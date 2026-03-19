#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <vector>
#include <string>
#include <fstream>
#include <sstream>
#include <queue>
#include <algorithm>
#include <cmath>
#include <climits>
#include <unordered_map>
#include <memory>

namespace py = pybind11;

// -------------------
struct Vector2 { int x; int y; };

bool sameVector(const Vector2& a, const Vector2& b) {
    return a.x == b.x && a.y == b.y;
}

// -------------------
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

    // FIX: téglalap ellenőrzés
    if (!matrix.empty()) {
        size_t w = matrix[0].size();
        for (const auto& row : matrix) {
            if (row.size() != w)
                throw std::runtime_error("CSV is not rectangular");
        }
    }

    return matrix;
}

// -------------------
struct Map {
    std::vector<std::vector<std::string>> map_data;
    std::string barrier_marker = "#";
    int width  = 0;
    int height = 0;

    explicit Map(const std::vector<std::vector<std::string>>& data) : map_data(data) {
        height = (int)map_data.size();
        width  = (height > 0) ? (int)map_data[0].size() : 0;
    }

    bool is_valid_pos(const Vector2& p) const {
        if (p.x < 0 || p.y < 0 || p.x >= width || p.y >= height) return false;
        return map_data[p.y][p.x] != barrier_marker;
    }
};

// -------------------
static std::unordered_map<std::string, std::shared_ptr<Map>> g_map_cache;

static std::shared_ptr<Map> get_cached_map(const std::string& csv_path) {
    auto it = g_map_cache.find(csv_path);
    if (it != g_map_cache.end()) return it->second;

    auto data = matrix_from_csv(csv_path);
    if (data.empty()) return nullptr;

    auto map_ptr = std::make_shared<Map>(data);
    g_map_cache[csv_path] = map_ptr;
    return map_ptr;
}

// -------------------
// SZOMSZÉDOK (corner cutting fix)
// -------------------
static std::vector<Vector2> get_neighbors(const Map& map, const Vector2& node) {
    static const int dirs[8][2] = {
        {-1,0},{1,0},{0,-1},{0,1},
        {-1,-1},{-1,1},{1,-1},{1,1}
    };

    std::vector<Vector2> result;
    result.reserve(8);

    for (int i = 0; i < 8; i++) {
        int dx = dirs[i][0];
        int dy = dirs[i][1];

        Vector2 n{ node.x + dx, node.y + dy };

        if (!map.is_valid_pos(n)) continue;

        // FIX: diagonális sarokvágás tiltása
        if (dx != 0 && dy != 0) {
            Vector2 n1{ node.x + dx, node.y };
            Vector2 n2{ node.x, node.y + dy };

            if (!map.is_valid_pos(n1) || !map.is_valid_pos(n2))
                continue;
        }

        result.push_back(n);
    }

    return result;
}

// -------------------
// HEURISZTIKA (Octile)
// -------------------
static int heuristic(const Vector2& a, const Vector2& b) {
    int dx = std::abs(a.x - b.x);
    int dy = std::abs(a.y - b.y);
    return 10 * std::max(dx, dy) + 4 * std::min(dx, dy);
}

// -------------------
struct OpenItem { int f; Vector2 pos; };
struct OpenCompare {
    bool operator()(const OpenItem& a, const OpenItem& b) const { return a.f > b.f; }
};

// -------------------
static std::vector<Vector2> astar(const Map& map, const Vector2& start, const Vector2& goal) {
    if (sameVector(start, goal)) return {start};
    if (!map.is_valid_pos(start) || !map.is_valid_pos(goal)) return {};

    std::priority_queue<OpenItem, std::vector<OpenItem>, OpenCompare> open_set;
    open_set.push({0, start});

    std::vector<std::vector<int>>     g_score(map.height, std::vector<int>(map.width, INT_MAX));
    std::vector<std::vector<Vector2>> parent(map.height, std::vector<Vector2>(map.width));
    std::vector<std::vector<bool>>    has_parent(map.height, std::vector<bool>(map.width, false));

    g_score[start.y][start.x] = 0;

    while (!open_set.empty()) {
        OpenItem item = open_set.top();
        open_set.pop();

        Vector2 current = item.pos;

        int expected_f = g_score[current.y][current.x] + heuristic(current, goal);
        if (item.f > expected_f) continue;

        if (sameVector(current, goal)) break;

        if (g_score[current.y][current.x] == INT_MAX) continue;

        for (const Vector2& neighbor : get_neighbors(map, current)) {

            int dx = std::abs(neighbor.x - current.x);
            int dy = std::abs(neighbor.y - current.y);

            int cost = (dx == 0 || dy == 0) ? 10 : 14;

            int tentative = g_score[current.y][current.x] + cost;

            if (tentative < g_score[neighbor.y][neighbor.x]) {
                parent[neighbor.y][neighbor.x] = current;
                has_parent[neighbor.y][neighbor.x] = true;
                g_score[neighbor.y][neighbor.x] = tentative;

                int f = tentative + heuristic(neighbor, goal);
                open_set.push({f, neighbor});
            }
        }
    }

    if (!has_parent[goal.y][goal.x]) return {};

    std::vector<Vector2> path;
    Vector2 cur = goal;

    while (has_parent[cur.y][cur.x]) {
        path.push_back(cur);
        cur = parent[cur.y][cur.x];
    }

    std::reverse(path.begin(), path.end());
    path.insert(path.begin(), start);

    return path;
}

// -------------------
// Python interface FIX
// -------------------
static Vector2 to_vec2(const py::object& obj) {
    if (!py::isinstance<py::tuple>(obj) && !py::isinstance<py::list>(obj))
        throw std::runtime_error("start/goal must be tuple/list");

    auto seq = py::cast<py::sequence>(obj);

    if (py::len(seq) != 2)
        throw std::runtime_error("start/goal must be (x,y)");

    return Vector2{ py::cast<int>(seq[0]), py::cast<int>(seq[1]) };
}

// -------------------
static std::vector<std::pair<int,int>> astar_from_csv_py(
    const std::string& csv_path,
    const py::object& start_obj,
    const py::object& goal_obj
) {
    auto map_ptr = get_cached_map(csv_path);
    if (!map_ptr) return {};

    Vector2 s = to_vec2(start_obj);
    Vector2 g = to_vec2(goal_obj);

    auto path = astar(*map_ptr, s, g);

    std::vector<std::pair<int,int>> out;

    if (path.size() < 2) return out;

    out.reserve(path.size() - 1);
    for (size_t i = 1; i < path.size(); i++) {
        out.emplace_back(path[i].x, path[i].y);
    }

    return out;
}

// -------------------
static void clear_map_cache() {
    g_map_cache.clear();
}

// -------------------
PYBIND11_MODULE(cpp_path, m) {
    m.doc() = "Optimized A* with diagonal fix and octile heuristic";

    m.def("astar_from_csv", &astar_from_csv_py,
          py::arg("csv_path"), py::arg("start"), py::arg("goal"));

    m.def("clear_map_cache", &clear_map_cache);
}