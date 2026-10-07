#!/bin/bash
# gen-image: generate / edit images through locally logged-in CLIs (no API key).
#   gpt -> Codex CLI built-in image tool (GPT Image 2, ChatGPT account quota)
#   nb  -> Antigravity CLI generate_image (Nano Banana, Google account quota)
set -uo pipefail

usage() {
  cat <<'EOF'
Usage: gen.sh -p "prompt" [-e gpt|nb|both] [-a 16:9] [-i ref.png]... [-o outdir] [-n count] [-t tag]
  -p  image prompt (required)
  -e  engine: gpt = GPT Image 2 via Codex | nb = Nano Banana via Antigravity | both   [default gpt]
  -a  aspect ratio: 1:1 16:9 9:16 4:3 3:4                                            [default 1:1]
  -i  reference / source image to edit (repeatable)
  -o  output directory                                                               [default ~/Pictures/AI生图]
  -n  images per engine, generated in parallel                                       [default 1]
  -t  file-name tag                                                                  [default timestamp]
Prints one "SAVED: <path>" line per image; exits 1 if nothing was produced.
EOF
}

ENGINE=gpt; PROMPT=""; ASPECT="1:1"; OUT="$HOME/Pictures/AI生图"; COUNT=1; TAG=""
REFS=()
while getopts "e:p:a:i:o:n:t:h" opt; do
  case $opt in
    e) ENGINE=$OPTARG ;; p) PROMPT=$OPTARG ;; a) ASPECT=$OPTARG ;;
    i) REFS+=("$OPTARG") ;; o) OUT=$OPTARG ;; n) COUNT=$OPTARG ;; t) TAG=$OPTARG ;;
    h) usage; exit 0 ;; *) usage; exit 2 ;;
  esac
done
[ -z "$PROMPT" ] && { usage; exit 2; }
case $ENGINE in gpt|nb|both) ;; *) echo "ERROR: unknown engine '$ENGINE'" >&2; exit 2 ;; esac
[ -z "$TAG" ] && TAG=$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT" || exit 2
OUT=$(cd "$OUT" && pwd)

ABS_REFS=()
for r in ${REFS[@]+"${REFS[@]}"}; do
  [ -f "$r" ] || { echo "ERROR: reference image not found: $r" >&2; exit 2; }
  ABS_REFS+=("$(cd "$(dirname "$r")" && pwd)/$(basename "$r")")
done
NREFS=${#ABS_REFS[@]}

find_codex() {
  command -v codex 2>/dev/null && return 0
  for c in /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex \
           /Applications/Codex.app/Contents/Resources/codex; do
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}
find_agy() {
  command -v agy 2>/dev/null && return 0
  [ -x "$HOME/.local/bin/agy" ] && { echo "$HOME/.local/bin/agy"; return 0; }
  return 1
}

CODEX_IMG_DIR="${CODEX_HOME:-$HOME/.codex}/generated_images"
AGY_BRAIN="$HOME/.gemini/antigravity-cli/brain"
RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/gen-image.XXXXXX")
MARK="$RUN_DIR/.mark"; touch "$MARK"; sleep 1

# copy_out <src> <engine> <k>  -> copies into OUT and records the path
copy_out() {
  local src=$1 eng=$2 k=$3 ext dest i=1
  ext="${src##*.}"
  dest="$OUT/${TAG}-${eng}-${k}.${ext}"
  while [ -e "$dest" ]; do dest="$OUT/${TAG}-${eng}-${k}_${i}.${ext}"; i=$((i+1)); done
  cp "$src" "$dest" && echo "$dest" >> "$RUN_DIR/saved"
}

newest_images_since_mark() {  # <dir>
  find "$1" -type f -newer "$MARK" \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) 2>/dev/null
}

run_gpt() {
  local k=$1 work log tid dir f found=0
  work="$RUN_DIR/gpt-$k"; mkdir -p "$work"; log="$work/log.jsonl"
  local note=""
  [ "$NREFS" -gt 0 ] && note=" Use the attached image(s) as the source / reference for this image."
  local instr="Use your built-in image generation tool to generate exactly one image. Do not write code, do not run shell commands, do not save or copy any files. Aspect ratio: ${ASPECT}. Image prompt: ${PROMPT}${note}"
  local args=(exec --skip-git-repo-check -s read-only -C "$work" --json)
  for r in ${ABS_REFS[@]+"${ABS_REFS[@]}"}; do args+=(-i "$r"); done
  "$CODEX" "${args[@]}" -- "$instr" > "$log" 2>&1
  tid=$(grep -o '"thread_id":"[^"]*"' "$log" | head -1 | cut -d'"' -f4)
  dir="$CODEX_IMG_DIR/$tid"
  [ -n "$tid" ] && [ -d "$dir" ] || dir="$CODEX_IMG_DIR"
  while IFS= read -r f; do [ -n "$f" ] && { copy_out "$f" gpt "$k"; found=1; }; done < <(newest_images_since_mark "$dir")
  [ $found -eq 1 ] || { echo "FAILED gpt-$k (log: $log)" >&2; tail -5 "$log" >&2; }
}

run_nb() {
  local k=$1 work log f found=0
  work="$RUN_DIR/nb-$k"; mkdir -p "$work"; log="$work/log.txt"
  local note=""
  if [ "$NREFS" -gt 0 ]; then
    local copies=() r
    for r in "${ABS_REFS[@]}"; do cp "$r" "$work/"; copies+=("$work/$(basename "$r")"); done
    note=" Use these image file(s) as the source / reference images (pass them to generate_image): ${copies[*]}"
  fi
  local instr="Call your generate_image tool exactly once with aspect_ratio \"${ASPECT}\". Do not write code and do not run shell commands. Image prompt: ${PROMPT}.${note} When finished, reply with only the absolute path of the generated image file."
  (cd "$work" && "$AGY" -p "$instr" --sandbox --print-timeout 600s) > "$log" 2>&1
  f=$(grep -oE '/[^ "`]+\.(png|jpg|jpeg|webp)' "$log" | grep '/antigravity-cli/brain/' | tail -1)
  if [ -n "$f" ] && [ -f "$f" ]; then
    copy_out "$f" nb "$k"; found=1
  else
    while IFS= read -r f; do [ -n "$f" ] && { copy_out "$f" nb "$k"; found=1; }; done < <(newest_images_since_mark "$AGY_BRAIN")
  fi
  [ $found -eq 1 ] || { echo "FAILED nb-$k (log: $log)" >&2; tail -5 "$log" >&2; }
}

if [ "$ENGINE" = gpt ] || [ "$ENGINE" = both ]; then
  CODEX=$(find_codex) || { echo "ERROR: Codex CLI not found (install ChatGPT/Codex app or: npm i -g @openai/codex; then: codex login)" >&2; exit 2; }
fi
if [ "$ENGINE" = nb ] || [ "$ENGINE" = both ]; then
  AGY=$(find_agy) || { echo "ERROR: Antigravity CLI not found (curl -fsSL https://antigravity.google/cli/install.sh | bash; then run agy once to sign in)" >&2; exit 2; }
fi

for k in $(seq 1 "$COUNT"); do
  { [ "$ENGINE" = gpt ] || [ "$ENGINE" = both ]; } && run_gpt "$k" &
  { [ "$ENGINE" = nb ] || [ "$ENGINE" = both ]; } && run_nb "$k" &
done
wait

if [ -s "$RUN_DIR/saved" ]; then
  while IFS= read -r p; do
    echo "SAVED: $p ($(sips -g pixelWidth -g pixelHeight "$p" 2>/dev/null | awk '/pixel/{print $2}' | paste -sd x -))"
  done < "$RUN_DIR/saved"
  exit 0
fi
echo "ERROR: no image produced (logs in $RUN_DIR)" >&2
exit 1
