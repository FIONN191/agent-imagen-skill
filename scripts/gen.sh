#!/bin/bash
# gen-image: generate / edit images.
#   gpt -> Codex CLI built-in image tool (GPT Image, ChatGPT account quota, no API key)
#   api -> OpenAI Images API via openai_image.py (GPT Image 2.6 etc., your API key, billed per use)
#   nb  -> Antigravity CLI generate_image (Nano Banana, Google account quota, no API key)
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

usage() {
  cat <<'EOF'
Usage: gen.sh -p "prompt" [-e gpt|api|nb|both|all|list] [-a 16:9] [-i ref.png]... [-o outdir] [-n count] [-t tag]
              [-r 1K|2K|4K] [-m model] [-q quality] [-c complexity] [-b background] [-f format] [-M mask.png]
  -p  image prompt (required)
  -e  engine: gpt = GPT Image via Codex | api = GPT Image via OpenAI API (your key, billed)
      nb = Nano Banana via Antigravity | both = gpt,nb | all = gpt,api,nb | or a list like api,nb   [default gpt]
  -a  aspect ratio: 1:1 16:9 9:16 4:3 3:4 (api: anything from 1:3 to 3:1, or auto)       [default 1:1;
      api edits without -a keep the first reference image's ratio]
  -i  reference / source image to edit (repeatable)
  -o  output directory                                                               [default ~/Pictures/AI生图]
  -n  images per engine, generated in parallel                                       [default 1]
  -t  file-name tag                                                                  [default timestamp]
 api only (defaults come from .env, see .env.example):
  -r  resolution: 1K | 2K | 4K (16:9 -> 1360x768 | 2560x1440 | 3840x2160)            [default 2K]
  -m  model: gpt-image-2.6-sunburst | gpt-image-2.6-flare | ... or sunburst | flare   [default gpt-image-2.6-sunburst]
  -q  quality: low | medium | high | xhigh | max | auto                               [default high]
  -c  complexity ("thinking" before drawing): low | medium | high                    [default: model default]
  -b  background: auto | opaque | transparent
  -f  format: png | jpeg | webp                                                      [default png]
  -M  mask PNG for inpainting (transparent = area to change, same size as the first -i image)
  Check the API setup without generating anything (free): python3 scripts/openai_image.py --check
Prints one "SAVED: <path> (<w>x<h>)" line per image; exits 1 if nothing was produced.
EOF
}

ENGINE=gpt; PROMPT=""; ASPECT="1:1"; ASPECT_SET=0; OUT="$HOME/Pictures/AI生图"; COUNT=1; TAG=""
RES=""; MODEL=""; QUALITY=""; COMPLEXITY=""; BACKGROUND=""; FORMAT=""; MASK=""
REFS=()
while getopts "e:p:a:i:o:n:t:r:m:q:c:b:f:M:h" opt; do
  case $opt in
    e) ENGINE=$OPTARG ;; p) PROMPT=$OPTARG ;; a) ASPECT=$OPTARG; ASPECT_SET=1 ;;
    i) REFS+=("$OPTARG") ;; o) OUT=$OPTARG ;; n) COUNT=$OPTARG ;; t) TAG=$OPTARG ;;
    r) RES=$OPTARG ;; m) MODEL=$OPTARG ;; q) QUALITY=$OPTARG ;; c) COMPLEXITY=$OPTARG ;;
    b) BACKGROUND=$OPTARG ;; f) FORMAT=$OPTARG ;; M) MASK=$OPTARG ;;
    h) usage; exit 0 ;; *) usage; exit 2 ;;
  esac
done
[ -z "$PROMPT" ] && { usage; exit 2; }

ENGINE=${ENGINE// /}
case $ENGINE in both) ENGINE=gpt,nb ;; all) ENGINE=gpt,api,nb ;; esac
USE_GPT=0; USE_API=0; USE_NB=0; ENGINE_LIST=()
IFS=',' read -ra ENGINE_LIST <<< "$ENGINE"
[ ${#ENGINE_LIST[@]} -gt 0 ] || { echo "ERROR: no engine given" >&2; exit 2; }
for e in "${ENGINE_LIST[@]}"; do
  case $e in
    gpt) USE_GPT=1 ;; api) USE_API=1 ;; nb) USE_NB=1 ;;
    *) echo "ERROR: unknown engine '$e' (use gpt, api, nb, both, all or a list like api,nb)" >&2; exit 2 ;;
  esac
done
case $COUNT in ''|*[!0-9]*|0) echo "ERROR: -n must be a positive integer" >&2; exit 2 ;; esac
[ -z "$TAG" ] && TAG=$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT" || exit 2
OUT=$(cd "$OUT" && pwd)

abs_path() { echo "$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; }
ABS_REFS=()
for r in ${REFS[@]+"${REFS[@]}"}; do
  [ -f "$r" ] || { echo "ERROR: reference image not found: $r" >&2; exit 2; }
  ABS_REFS+=("$(abs_path "$r")")
done
NREFS=${#ABS_REFS[@]}
ABS_MASK=""
if [ -n "$MASK" ]; then
  [ -f "$MASK" ] || { echo "ERROR: mask not found: $MASK" >&2; exit 2; }
  [ "$NREFS" -gt 0 ] || { echo "ERROR: -M needs the image to edit (-i)" >&2; exit 2; }
  [ $USE_API -eq 1 ] || echo "NOTE: -M (mask) only applies to the api engine; ignored" >&2
  ABS_MASK=$(abs_path "$MASK")
fi

PY=$(command -v python3 2>/dev/null || true)
img_dims() {  # <file> -> WxH
  if command -v sips >/dev/null 2>&1; then
    sips -g pixelWidth -g pixelHeight "$1" 2>/dev/null | awk '/pixel/{print $2}' | paste -sd x -
  elif [ -n "$PY" ]; then
    "$PY" "$SCRIPT_DIR/openai_image.py" --dims "$1" 2>/dev/null
  fi
}

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

# One API call covers all -n images; openai_image.py appends "path<TAB>WxH" lines to the saved list.
API_ARGS=(--prompt="$PROMPT" -n "$COUNT" -o "$OUT" --tag="$TAG" --record "$RUN_DIR/saved")
[ $ASPECT_SET -eq 1 ] && API_ARGS+=(--aspect="$ASPECT")
[ -n "$RES" ] && API_ARGS+=(-r "$RES")
[ -n "$MODEL" ] && API_ARGS+=(-m "$MODEL")
[ -n "$QUALITY" ] && API_ARGS+=(-q "$QUALITY")
[ -n "$COMPLEXITY" ] && API_ARGS+=(-c "$COMPLEXITY")
[ -n "$BACKGROUND" ] && API_ARGS+=(-b "$BACKGROUND")
[ -n "$FORMAT" ] && API_ARGS+=(-f "$FORMAT")
[ -n "$ABS_MASK" ] && API_ARGS+=(--mask "$ABS_MASK")
for r in ${ABS_REFS[@]+"${ABS_REFS[@]}"}; do API_ARGS+=(-i "$r"); done

run_api() {
  local work="$RUN_DIR/api" rc
  mkdir -p "$work"
  "$PY" "$SCRIPT_DIR/openai_image.py" "${API_ARGS[@]}" > "$work/out.txt" 2> "$work/log.txt"
  rc=$?
  cat "$work/log.txt" >&2  # model / size / timing, or the error with hints
  [ $rc -eq 0 ] || echo "FAILED api (log: $work/log.txt)" >&2
}

if [ $USE_GPT -eq 1 ]; then
  CODEX=$(find_codex) || { echo "ERROR: Codex CLI not found (install ChatGPT/Codex app or: npm i -g @openai/codex; then: codex login)" >&2; exit 2; }
fi
if [ $USE_NB -eq 1 ]; then
  AGY=$(find_agy) || { echo "ERROR: Antigravity CLI not found (curl -fsSL https://antigravity.google/cli/install.sh | bash; then run agy once to sign in)" >&2; exit 2; }
fi
if [ $USE_API -eq 1 ]; then
  [ -n "$PY" ] || { echo "ERROR: python3 not found (needed for -e api; on macOS run: xcode-select --install)" >&2; exit 2; }
  # validates the key, options and reference images before anything is started or billed
  "$PY" "$SCRIPT_DIR/openai_image.py" "${API_ARGS[@]}" --preflight || exit 2
fi

[ $USE_API -eq 1 ] && run_api &
for k in $(seq 1 "$COUNT"); do
  [ $USE_GPT -eq 1 ] && run_gpt "$k" &
  [ $USE_NB -eq 1 ] && run_nb "$k" &
done
wait

if [ -s "$RUN_DIR/saved" ]; then
  while IFS=$'\t' read -r p d; do
    [ -n "$p" ] || continue
    [ -n "${d:-}" ] || d=$(img_dims "$p")
    echo "SAVED: $p ($d)"
  done < "$RUN_DIR/saved"
  exit 0
fi
echo "ERROR: no image produced (logs in $RUN_DIR)" >&2
exit 1
