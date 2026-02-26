// Alap kiírás, debug (std::cout, std::endl)
#include <iostream>

// Dinamikus tömb (std::vector)
#include <vector>

// Priority queue (open_set)
#include <queue>

// Algoritmusok (std::reverse, std::min, std::max)
#include <algorithm>

// Matematikai függvények (std::abs)
#include <cmath>

// Egész szám határok (INT_MAX)
#include <climits>

// (Opcionális, később) unordered_map, ha majd visszatérünk rá
#include <unordered_map>

// (Opcionális) set / unordered_set (closed set-hez)
#include <set>
#include <unordered_set>
#include <string>
#include <fstream>
#include <sstream>

// CSV sor feldarabolása vessző mentén
static std::vector<std::string> split_csv_row(const std::string& line) {
    std::vector<std::string> cells;
    std::stringstream ss(line);
    std::string cell;

    while (std::getline(ss, cell, ',')) {
        // Ha a CSV-ben van szóköz, ezt le lehet trimmelni (most nem muszáj)
        cells.push_back(cell);
    }
    return cells;
}

// Python: matrix_from_csv(csv_path) megfelelője
std::vector<std::vector<std::string>> matrix_from_csv(const std::string& csv_path) {

    std::ifstream file(csv_path);
    if (!file.is_open()) {
        std::cout << "Cannot open: " << csv_path << "\n";
        return {};
    }

    std::vector<std::vector<std::string>> matrix;

    std::string line;
    while (std::getline(file, line)) {
        // üres sor skip
        if (line.empty()) continue;

        matrix.push_back(split_csv_row(line));
    }

    return matrix;
}



struct Vector2 {
    int x; 
    int y;
};

//egyszerü hasonlítás (ez a forma nem dob hibát) 
bool sameVector(const Vector2& a, const Vector2& b) {
    return a.x == b.x && a.y == b.y;
}

//térkép / pálya 
struct Map {
    //  rács adatok
    std::vector<std::vector<std::string>> map_data;

    // markerek (Python defaultok) 
    std::string path_marker = ".";
    std::string barrier_marker = "#";
    std::string rover_marker = "S";
    std::vector<std::string> mineral_markers = {"B", "Y", "G"};

    int width = 0;
    int height = 0;

    std::unordered_map<std::string, std::string> marker_descriptions = {
        {"S", "Rover Start"},
        {".", "Field"},
        {"#", "Barrier"},
        {"Y", "Gold"},
        {"B", "Ice"},
        {"G", "Green"}
    };

    // Konstruktor: átveszi a beolvasott map_data-t
    Map(const std::vector<std::vector<std::string>>& data)
        : map_data(data)
    {
        height = (int)map_data.size();
        width  = (height > 0) ? (int)map_data[0].size() : 0;
    }

    //get_tile(position)
    std::string get_tile(const Vector2& position) const {
        return map_data[position.y][position.x];
    }

    // Valid pozíció ami nem fal 
    bool is_valid_pos(const Vector2& p) const {
        if (p.x < 0 || p.y < 0 || p.x >= width || p.y >= height) return false;
        // akadály kizárása
        return map_data[p.y][p.x] != barrier_marker;
    }



    // Ee pythonbol limit=-1 volt de c-be könyebb igy szoval - limit=1: 
    std::vector<Vector2> get_poses_of_tile(const std::string& tile_name, int limit = -1) const {
        std::vector<Vector2> found;

        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                if (map_data[y][x] == tile_name) {
                    found.push_back({x, y});
                    if (limit > 0 && (int)found.size() >= limit) {
                        return found; // ha limit=1 akkor vissza ad egy egy elemű listát
                    }
                }
            }
        }
        return found;
    }
};


// szomszédok és irony
std::vector<Vector2> get_neighbors(const Map& map, const Vector2& node) {

    // 8 irány amibe mozoghat a rover
    static const int dirs[8][2] = {
        {-1,0},{1,0},{0,-1},{0,1},
        {-1,-1},{-1,1},{1,-1},{1,1}
    };

    std::vector<Vector2> result;
    result.reserve(8);

    //megnézzük minden irányba ,hogy rajta van-e a mappon
    for (int i = 0; i < 8; i++) {
        Vector2 n{ node.x + dirs[i][0], node.y + dirs[i][1] };
        if (map.is_valid_pos(n)) {
            result.push_back(n);
        }
    }
    return result;
}

// manhattan fajta minimum távolság számítás
int heuristic(const Vector2& a, const Vector2& b) {
    return std::abs(a.x - b.x) + std::abs(a.y - b.y);
}


struct OpenItem {
    int f;        // f = g + h
    Vector2 pos;  // aktuális pont
};

// mivel nekünk a legkisebb kell a C++ meg a legnagyobbat teszi lőre
struct OpenCompare {
    bool operator()(const OpenItem& a, const OpenItem& b) const {
        return a.f > b.f;
    }
};

//A* algoritmus

std::vector<Vector2> astar( Map& map , Vector2& start , Vector2& goal){
    //priority queue
    std::priority_queue < OpenItem,std::vector<OpenItem>,OpenCompare > open_set;


    open_set.push({0, start});

    //eleinte végtelen
    std::vector<std::vector<int>> g_score(map.height,std::vector<int>(map.width, INT_MAX));
    std::vector<std::vector<Vector2>> parent(map.height,std::vector<Vector2>(map.width));
    std::vector<std::vector<bool>> has_parent(map.height,std::vector<bool>(map.width, false)); // mar van parent
    
    g_score[start.y][start.x] = 0;

    while (!open_set.empty()) {
        Vector2 current = open_set.top().pos;
        open_set.pop();
    
        if(sameVector(current,goal)){ // ha elértük a célt kilépünk
            break;
        }
    


        //bejárjuk a szomszédokat 
        for (const Vector2& neighbor : get_neighbors(map, current)) {
            int tentative = g_score[current.y][current.x] + 1;

            // neighbor cellához kell job ut
            if (tentative < g_score[neighbor.y][neighbor.x]) {
                parent[neighbor.y][neighbor.x] = current;
                has_parent[neighbor.y][neighbor.x] = true;
                g_score[neighbor.y][neighbor.x] = tentative;
                int f = tentative + heuristic(neighbor, goal);
                open_set.push({f, neighbor});
            }
        }
    }


    //vissza fejtjük az utvonalat
    std:: vector<Vector2> path;
    Vector2 cur = goal;
    
    while(has_parent[cur.y][cur.x]){
        path.push_back(cur);
        cur = parent[cur.y][cur.x];
    }

    std:: reverse(path.begin(), path.end());

    return path;
}


int main() {
    auto data = matrix_from_csv("../data/mars_map_50x50.csv");   
    
    std::cout << "rows=" << data.size() << "\n";
    if (!data.empty()) std::cout << "cols=" << data[0].size() << "\n";

    Map map(data);

    // start: 'S' pozíció
    auto starts = map.get_poses_of_tile("S", 1);
    if (starts.empty()) {
        std::cout << "No S (start) found!\n";
        return 0;
    }
    Vector2 start = starts[0];

    // cél: pl. első 'Y' (gold)
    auto goals = map.get_poses_of_tile("Y", 1);
    if (goals.empty()) {
        std::cout << "No Y found!\n";
        return 0;
    }
    Vector2 goal = goals[0];

    // itt hívod az A*-t (a te astar függvényed)
    // auto path = astar(map, start, goal);

    std::cout << "Map loaded: " << map.width << "x" << map.height << "\n";
    std::cout << "Start S: (" << start.x << "," << start.y << ")\n";
    std::cout << "Goal Y: (" << goal.x << "," << goal.y << ")\n";
}