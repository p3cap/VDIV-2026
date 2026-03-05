#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
// include flag ,tasks.js
#include <vector>
#include <string>
#include <fstream>
#include <sstream>
#include <queue>
#include <algorithm>
#include <cmath>
#include <climits>

namespace py = pybind11;

// -------------------
// A te típusaid / logikád
// -------------------
struct Vector2 { int x; int y; };

bool sameVector(const Vector2& a, const Vector2& b) {
    return a.x == b.x && a.y == b.y;
}

static std::string trim(std::string s) {
    while (!s.empty() && (s.back() == '\r' || s.back() == '\n' || s.back() == ' ' || s.back() == '\t'))
        s.pop_back();
    size_t i = 0;
    while (i < s.size() && (s[i] == ' ' || s[i] == '\t'))
        i++;
    return s.substr(i);
}

static std::vector<std::string> split_csv_row(const std::string& line) {
    std::vector<std::string> cells;
    std::stringstream ss(line);
    std::string cell;
    while (std::getline(ss, cell, ',')) {
        cells.push_back(trim(cell));
    }
    return cells;
}

static std::vector<std::vector<std::string>> matrix_from_csv(const std::string& csv_path) {
    std::ifstream file(csv_path);
    if (!file.is_open()) return {};

    std::vector<std::vector<std::string>> matrix;
    std::string line;
    while (std::getline(file, line)) {
        if (line.empty()) continue;
        matrix.push_back(split_csv_row(line));
    }
    return matrix;
}

struct Map {
    std::vector<std::vector<std::string>> map_data;
    std::string barrier_marker = "#";
    int width = 0;
    int height = 0;

    explicit Map(const std::vector<std::vector<std::string>>& data) : map_data(data) {
        height = (int)map_data.size();
        width  = (height > 0) ? (int)map_data[0].size() : 0;
    }

    bool is_valid_pos(const Vector2& p) const {
        if (p.x < 0 || p.y < 0 || p.x >= width || p.y >= height) return false;
        return map_data[p.y][p.x] != barrier_marker;
    }

    std::vector<Vector2> get_poses_of_tile(const std::string& tile_name, int limit = -1) const {
        std::vector<Vector2> found;
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                if (map_data[y][x] == tile_name) {
                    found.push_back({x, y});
                    if (limit > 0 && (int)found.size() >= limit) return found;
                }
            }
        }
        return found;
    }
};

static std::vector<Vector2> get_neighbors(const Map& map, const Vector2& node) {
    static const int dirs[8][2] = {
        {-1,0},{1,0},{0,-1},{0,1},
        {-1,-1},{-1,1},{1,-1},{1,1}
    };

    std::vector<Vector2> result;
    result.reserve(8);

    for (int i = 0; i < 8; i++) {
        Vector2 n{ node.x + dirs[i][0], node.y + dirs[i][1] };
        if (map.is_valid_pos(n)) result.push_back(n);
    }
    return result;
}

static int heuristic(const Vector2& a, const Vector2& b) {
    return std::abs(a.x - b.x) + std::abs(a.y - b.y);
}

struct OpenItem { int f; Vector2 pos; };
struct OpenCompare {
    bool operator()(const OpenItem& a, const OpenItem& b) const { return a.f > b.f; }
};

static std::vector<Vector2> astar(const Map& map, const Vector2& start, const Vector2& goal) {
    if (sameVector(start, goal)) return {start};
    if (!map.is_valid_pos(start) || !map.is_valid_pos(goal)) return {};

    std::priority_queue<OpenItem, std::vector<OpenItem>, OpenCompare> open_set;
    open_set.push({0, start});

    std::vector<std::vector<int>> g_score(map.height, std::vector<int>(map.width, INT_MAX));
    std::vector<std::vector<Vector2>> parent(map.height, std::vector<Vector2>(map.width));
    std::vector<std::vector<bool>> has_parent(map.height, std::vector<bool>(map.width, false));

    g_score[start.y][start.x] = 0;

    bool reached_goal = false;

    while (!open_set.empty()) {
        Vector2 current = open_set.top().pos;
        open_set.pop();

        if (sameVector(current, goal)) {
            reached_goal = true;
            break;
        }

        for (const Vector2& neighbor : get_neighbors(map, current)) {
            int tentative = g_score[current.y][current.x] + 1;

            if (tentative < g_score[neighbor.y][neighbor.x]) {
                parent[neighbor.y][neighbor.x] = current;
                has_parent[neighbor.y][neighbor.x] = true;
                g_score[neighbor.y][neighbor.x] = tentative;

                int f = tentative + heuristic(neighbor, goal);
                open_set.push({f, neighbor});
            }
        }
    }

    if (!reached_goal) return {};

    std::vector<Vector2> path;
    Vector2 cur = goal;

    while (has_parent[cur.y][cur.x]) {
        path.push_back(cur);
        cur = parent[cur.y][cur.x];
    }

    std::reverse(path.begin(), path.end());
    path.insert(path.begin(), start); // start is benne legyen

    return path;
}

// -------------------
// Python-barát wrapper
// -------------------


// Python (x,y) -> Vector2
static Vector2 to_vec2(const py::object& obj) {
    auto seq = py::cast<py::sequence>(obj);
    if (py::len(seq) != 2) throw std::runtime_error("start/goal must be (x,y)");
    return Vector2{ py::cast<int>(seq[0]), py::cast<int>(seq[1]) };
}

// Wrapper: Pythonból ezt hívod
// Visszaad list[tuple[int,int]]-et
static std::vector<std::pair<int,int>> astar_from_csv_py(
    const std::string& csv_path,
    const py::object& start_obj,
    const py::object& goal_obj
) {
    // feltételezem, hogy nálad már megvan:
    // auto data = matrix_from_csv(csv_path);
    // Map map(data);

    auto data = matrix_from_csv(csv_path);
    if (data.empty()) return {};

    Map map(data);

    Vector2 start = to_vec2(start_obj);
    Vector2 goal  = to_vec2(goal_obj);

    // FONTOS: a te astar signature-öd most ilyen:
    // std::vector<Vector2> astar(Map& map, Vector2& start, Vector2& goal)
    // ezért csinálunk másolatot, hogy ne reference-elt ideiglenes legyen
    Vector2 s = start;
    Vector2 g = goal;

    auto path = astar(map, s, g);

    std::vector<std::pair<int,int>> out;
    out.reserve(path.size());
    for (const auto& p : path) out.emplace_back(p.x, p.y);
    return out;
}

PYBIND11_MODULE(cpp_path, m) {
    m.doc() = "C++ A* pathfinding for MarsRover";

    m.def("astar_from_csv", &astar_from_csv_py,
          py::arg("csv_path"), py::arg("start"), py::arg("goal"),
          "Run A* on a CSV map. start/goal are (x,y). Returns list of (x,y).");
}