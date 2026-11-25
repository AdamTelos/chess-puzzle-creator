import glob
import re
import chess.pgn

# 1. Gather all 17 of your generated puzzle files
files = sorted(
    glob.glob("exact_repertoire_puzzles_*.pgn"),
    key=lambda x: int(x.split('_')[-1].split('.')[0])
)

all_games = []
print(f"Reading puzzles from {len(files)} files...")

# 2. Extract every individual game out of the files
for f_name in files:
    with open(f_name, "r", encoding="utf-8") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            all_games.append(game)

print(f"✅ Successfully loaded {len(all_games)} total puzzles.")

# Helper function to extract the numeric rating out of the PGN "Event" tag
def get_rating(game_node):
    event_str = game_node.headers.get("Event", "")
    match = re.search(r"Rating\s+(\d+)", event_str)
    if match:
        return int(match.group(1))
    return 0  # Fallback baseline if a rating is somehow missing

# 3. Sort all games globally by rating (Lowest/Easiest to Highest/Hardest)
print("Sorting all puzzles by rating for a progressive difficulty curve...")
all_games.sort(key=get_rating)

# 4. Repackage into clean batches of exactly 64
puzzles_per_study = 64
file_num = 1

print("\nGenerating your progressive Lichess volumes:")
for i in range(0, len(all_games), puzzles_per_study):
    batch = all_games[i:i+puzzles_per_study]
    output_filename = f"lichess_study_ready_vol_{file_num}.pgn"

    with open(output_filename, "w", encoding="utf-8") as out_file:
        for game in batch:
            print(game, file=out_file, end="\n\n")

    # Calculate the rating range inside this specific chunk
    min_rating = get_rating(batch[0])
    max_rating = get_rating(batch[-1])

    print(f"📁 Created {output_filename} | Puzzles: {len(batch)} | Rating Range: {min_rating} → {max_rating}")
    file_num += 1

print("\n🎉 All done! Your files are now perfectly ordered by difficulty.")