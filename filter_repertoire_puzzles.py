import csv
import json
import time
import requests
import chess.pgn

# ---------------------------------------------------------
# Step 1: Parse Your Repertoire PGN and Map Exact Move Sequences
# ---------------------------------------------------------
def extract_san_lines(node, board=None, current_line=None):
    if current_line is None:
        current_line = []
    if board is None:
        board = chess.Board()

    lines = []
    if node.move:
        try:
            san_move = board.san(node.move)
            current_line.append(san_move)
            board.push(node.move)
        except Exception:
            return lines

    if not node.variations:
        lines.append(list(current_line))
    else:
        for var in node.variations:
            lines.extend(extract_san_lines(var, board.copy(), list(current_line)))

    return lines

print("Parsing your repertoire PGN file...")
try:
    with open("white_repertoire.pgn", "r", encoding="utf-8") as f:
        repertoire_game = chess.pgn.read_game(f)
    if repertoire_game is None:
        print("❌ Error: The file 'white_repertoire.pgn' appears to be empty or an invalid PGN.")
        exit()
    repertoire_lines = extract_san_lines(repertoire_game.root())
    print(f"✅ Successfully mapped {len(repertoire_lines)} exact variation pathways.")
except FileNotFoundError:
    print("❌ Error: 'white_repertoire.pgn' file not found in this directory.")
    exit()

# ---------------------------------------------------------
# Step 2: Scan Lichess Puzzle CSV (With ALL your requested tags)
# ---------------------------------------------------------
csv_path = "lichess_db_puzzle.csv"
candidates = []

print("Scanning Lichess Puzzle Database (Applying comprehensive 1.d4 gateway filters)...")

TARGET_KEYWORDS = [
    "Queen's Pawn",
    "Catalan",
    "Open Defense",
    "Classical Line",
    "English Opening",
    "Englund Gambit",
    "King's Indian",
    "Queen's Gambit Accepted",
    "Queen's Gambit Declined",
    "Slav Defense",
    "Dutch Defense",
    "Benoni"
]

try:
    with open(csv_path, mode="r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            opening_tags = row.get("OpeningTags", "")
            if opening_tags and opening_tags != "null":
                if any(kw.lower() in opening_tags.lower() for kw in TARGET_KEYWORDS):
                    game_url = row["GameUrl"]
                    game_id = game_url.split("/")[-1].split("#")[0]
                    if len(game_id) == 8:
                        candidates.append((game_id, row))

    print(f"✅ Filtered down to {len(candidates)} total umbrella games to verify via API.")
except FileNotFoundError:
    print(f"❌ Error: '{csv_path}' file not found.")
    exit()

# ---------------------------------------------------------
# Steps 3 & 4: Verify Move Histories & Save INCREMENTALLY
# ---------------------------------------------------------
def matches_repertoire(game_moves_list, repertoire_lines):
    for line in repertoire_lines:
        n = len(line)
        if len(game_moves_list) >= n:
            if game_moves_list[:n] == line:
                return True
        else:
            if game_moves_list == line[:len(game_moves_list)]:
                return True
    return False

matching_puzzles_count = 0
puzzles_per_file = 20
file_num = 1
outfile = None

print("\nVerifying move histories and saving exact matches instantly to disk...")
batch_size = 300

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
                    game_moves = moves_str.split()

                    if matches_repertoire(game_moves, repertoire_lines):
                        row = id_to_row[g_id]

                        if matching_puzzles_count % puzzles_per_file == 0:
                            if outfile:
                                outfile.close()
                            outfile = open(f"exact_repertoire_puzzles_{file_num}.pgn", "w", encoding="utf-8")
                            file_num += 1

                        # Build and write the puzzle data
                        game = chess.pgn.Game()
                        game.headers["Event"] = f"Exact Repertoire Puzzle - Rating {row['Rating']}"
                        game.headers["Site"] = row["GameUrl"]
                        game.headers["SetUp"] = "1"
                        game.headers["FEN"] = row["FEN"]
                        game.headers["Result"] = "*"

                        # FIX: Using node.add_variation() for strict backwards-compatibility
                        node = game
                        for move_uci in row["Moves"].split():
                            node = node.add_variation(chess.Move.from_uci(move_uci))

                        print(game, file=outfile, end="\n\n")
                        outfile.flush() # Instantly writes to your hard drive item-by-item

                        matching_puzzles_count += 1

            print(f"Progress: Checked {min(i + batch_size, len(candidates))}/{len(candidates)} games. Matches saved so far: {matching_puzzles_count}")

        elif response.status_code == 429:
            print("⚠️ Rate limited by Lichess API. Pausing for 60 seconds to cool down...")
            time.sleep(60)
            i -= batch_size
        else:
            print(f"⚠️ API encountered error: Status {response.status_code}")

    except Exception as e:
        print(f"⚠️ Error processing batch: {e}")

    time.sleep(0.1)

if outfile:
    outfile.close()

print(f"\n🎉 Done! {matching_puzzles_count} total custom puzzles have been fully processed and saved to your folder.")