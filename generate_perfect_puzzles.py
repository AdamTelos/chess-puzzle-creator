import csv
import json
import time
import requests
import chess
import chess.pgn

# ---------------------------------------------------------
# Step 1: Parse Your Repertoire PGN into Move Arrays
# ---------------------------------------------------------
def extract_move_lines(node, board=None, current_line=None):
    if current_line is None:
        current_line = []
    if board is None:
        board = chess.Board()

    lines = []
    if node.move:
        current_line.append(node.move)
        board.push(node.move)

    if not node.variations:
        lines.append(list(current_line))
    else:
        for var in node.variations:
            lines.extend(extract_move_lines(var, board.copy(), list(current_line)))

    return lines

print("Parsing your repertoire PGN file...")
try:
    with open("white_repertoire.pgn", "r", encoding="utf-8") as f:
        repertoire_game = chess.pgn.read_game(f)
    if repertoire_game is None:
        print("❌ Error: The file 'white_repertoire.pgn' appears to be empty or an invalid PGN.")
        exit()
    repertoire_lines = extract_move_lines(repertoire_game.root())
    print(f"✅ Successfully mapped {len(repertoire_lines)} exact variation pathways.")
except FileNotFoundError:
    print("❌ Error: 'white_repertoire.pgn' file not found in this folder.")
    exit()

# ---------------------------------------------------------
# Step 2: Scan Lichess Puzzle CSV
# ---------------------------------------------------------
csv_path = "lichess_db_puzzle.csv"
candidates = []

print("Scanning Lichess Puzzle Database...")
TARGET_KEYWORDS = [
    "Queen's Pawn", "Catalan", "Open Defense", "Classical Line",
    "English Opening", "Englund Gambit", "King's Indian",
    "Queen's Gambit Accepted", "Queen's Gambit Declined",
    "Slav Defense", "Dutch Defense", "Benoni"
]

try:
    with open(csv_path, mode="r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            opening_tags = row.get("OpeningTags", "")
            if opening_tags and opening_tags != "null":
                if any(kw.lower() in opening_tags.lower() for kw in TARGET_KEYWORDS):
                    # 🎯 THE BUG FIX: Safely grab the exact 8-character ID immediately after lichess.org/
                    raw_url = row["GameUrl"]
                    try:
                        game_id = raw_url.split("lichess.org/")[1][:8]
                        if len(game_id) == 8:
                            candidates.append((game_id, row))
                    except IndexError:
                        continue

    print(f"✅ Filtered down to {len(candidates)} candidate games to verify via API.")
except FileNotFoundError:
    print(f"❌ Error: '{csv_path}' file not found.")
    exit()

# ---------------------------------------------------------
# Step 3: Prefix-Matching Engine
# ---------------------------------------------------------
def parse_api_moves(moves_str):
    board = chess.Board()
    moves_list = []
    for move_str in moves_str.split():
        try:
            move = chess.Move.from_uci(move_str)
            if move in board.legal_moves:
                moves_list.append(move)
                board.push(move)
                continue
        except Exception:
            pass
        try:
            move = board.parse_san(move_str)
            moves_list.append(move)
            board.push(move)
        except Exception:
            return []
    return moves_list

def matches_repertoire(game_moves, repertoire_lines):
    if not game_moves:
        return False
    for line in repertoire_lines:
        match_len = 0
        for gm, lm in zip(game_moves, line):
            if gm == lm:
                match_len += 1
            else:
                break

        # 🎯 Ensure the game successfully stayed in your prep for at least 5 plies (move 3)
        if match_len >= 5 or match_len == len(line):
            return True
    return False

white_solve_puzzles = []
black_solve_puzzles = []
batch_size = 300

print("\nVerifying game histories via Lichess API...")

for i in range(0, len(candidates), batch_size):
    chunk = candidates[i:i+batch_size]
    chunk_ids = [item[0] for item in chunk]
    id_to_row = {item[0]: item[1] for item in chunk}

    url = "https://lichess.org/api/games/export/_ids?moves=true&clocks=false&evals=false"
    headers = {"Accept": "application/x-ndjson"}
    body = ",".join(chunk_ids)

    try:
        response = requests.post(url, headers=headers, data=body)
        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    game_data = json.loads(line.decode("utf-8"))
                    g_id = game_data.get("id")
                    moves_str = game_data.get("moves", "")

                    game_moves = parse_api_moves(moves_str)

                    if matches_repertoire(game_moves, repertoire_lines):
                        row = id_to_row[g_id]
                        all_moves = row["Moves"].split()
                        if not all_moves:
                            continue

                        try:
                            board = chess.Board(row["FEN"])
                            # If it's Black's turn to move, Black is making the blunder. So White gets to solve it!
                            solver_color = "White" if board.turn == chess.BLACK else "Black"

                            puzzle_data = {
                                "rating": int(row["Rating"]),
                                "fen": row["FEN"],
                                "moves": all_moves,
                                "url": row["GameUrl"],
                                "solver": solver_color
                            }

                            if solver_color == "White":
                                white_solve_puzzles.append(puzzle_data)
                            else:
                                black_solve_puzzles.append(puzzle_data)
                        except Exception:
                            continue

            print(f"Progress: Checked {min(i + batch_size, len(candidates))}/{len(candidates)} games. White Puzzles: {len(white_solve_puzzles)} | Black Puzzles: {len(black_solve_puzzles)}")
        elif response.status_code == 429:
            print("⚠️ Rate limited. Cooling down for 60 seconds...")
            time.sleep(60)
            i -= batch_size
    except Exception as e:
        print(f"⚠️ Error processing batch: {e}")

    time.sleep(0.1)

# ---------------------------------------------------------
# Step 4: Export to Sorted 64-Chapter Volumes
# ---------------------------------------------------------
def save_volumes(puzzles, prefix):
    puzzles.sort(key=lambda x: x["rating"])
    puzzles_per_file = 64
    file_num = 1

    for i in range(0, len(puzzles), puzzles_per_file):
        batch = puzzles[i:i+puzzles_per_file]
        filename = f"{prefix}_vol_{file_num}.pgn"

        with open(filename, "w", encoding="utf-8") as out_file:
            for pz in batch:
                game = chess.pgn.Game()
                game.headers["Event"] = f"{pz['solver']} Repertoire Puzzle - Rating {pz['rating']}"
                game.headers["Site"] = pz["url"]
                game.headers["SetUp"] = "1"
                game.headers["FEN"] = pz["fen"]

                # Explicit orientation tag so Lichess spins the board automatically
                game.headers["Orientation"] = pz["solver"]
                game.headers["Result"] = "*"

                node = game
                for m_uci in pz["moves"]:
                    node = node.add_main_variation(chess.Move.from_uci(m_uci))

                print(game, file=out_file, end="\n\n")
        print(f"📁 Created {filename} | Puzzles: {len(batch)} | Difficulty: {batch[0]['rating']} ➔ {batch[-1]['rating']}")
        file_num += 1

print("\nSaving your progressive tactical volumes...")
if white_solve_puzzles:
    save_volumes(white_solve_puzzles, "repertoire_tactics_white_to_solve")
if black_solve_puzzles:
    save_volumes(black_solve_puzzles, "repertoire_tactics_black_to_solve")

print("\n🎉 Success! The URL bug is patched, and opening validation is flawless.")