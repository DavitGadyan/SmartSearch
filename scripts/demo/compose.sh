#!/usr/bin/env bash
# Builds the demo video: title card -> scenes with lower-third captions -> outro, cross-faded, 1080p H.264.
# Text is rendered by overlays.py (Pillow) and composited with ffmpeg's overlay filter, so no drawtext is needed.
# Usage: bash compose.sh <repo_root>   (expects raw/<scene>.webm from record.js)
set -euo pipefail
cd "$(dirname "$0")"
ROOT="${1:-/Users/dyada/Desktop/Github/SmartSearch}"
OUT_DIR="$ROOT/docs/demo"; mkdir -p "$OUT_DIR" work
BG="$ROOT/frontend/public/img/bg/liquid.webp"
PY="uv run --project $ROOT/backend python"
FPS=30; W=1920; H=1080; XF=0.6

# scene | speed | title | subtitle
SCENES=(
  "home|1.0|Storefront|42,994 real products, hybrid search, personalized rails"
  "search|1.3|Search and ranking|BM25 + embeddings fused, LightGBM LambdaRank, every result explains its score"
  "product|1.0|Product page and recommendations|Similar, Goes with it, Bought together: embeddings, co-purchase, knowledge graph|3.5"
  "assistant|1.3|Shopping assistant|Claude tool-use over the store's own APIs; it adds to the cart when asked"
  "checkout|1.0|Agentic Commerce Protocol|Checkout sessions and delegated payment: the same path an AI agent uses"
  "console|1.0|Merchant console|Behind a keyword: KPIs, funnel, search terms, ranking quality"
  "experiments|1.0|A/B experiments|Sticky assignment, z-tests, CUPED, SRM check, power, verdict: ship, keep running or reject"
  "builder|1.3|An experiment from one sentence|The console assistant drafts both arms, plans the sample size, deploys and reports H0"
)
: > work/scenes.tsv
for spec in "${SCENES[@]}"; do IFS='|' read -r name speed title sub _ <<< "$spec"; printf '%s\t%s\t%s\n' "$name" "$title" "$sub" >> work/scenes.tsv; done
$PY overlays.py work work/scenes.tsv

card() { # name seconds  (backdrop slow zoom under a light veil, text layer fades in)
  local name=$1 secs=$2 frames=$(( $2 * FPS ))
  ffmpeg -y -loglevel error -loop 1 -framerate $FPS -i "$BG" -loop 1 -framerate $FPS -i "work/${name}_text.png" -t "$secs" -filter_complex "\
[0:v]scale=2304:1296,zoompan=z='1+0.00045*on':d=$frames:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=${W}x${H}:fps=$FPS,drawbox=c=white@0.42:t=fill,fade=t=in:st=0:d=0.6[bg];\
[1:v]format=rgba,fade=t=in:st=0.4:d=0.9:alpha=1[txt];[bg][txt]overlay=0:0:shortest=1,format=yuv420p[v]" \
    -map "[v]" -r $FPS -c:v libx264 -preset medium -crf 18 "work/${name}.mp4"
}
card intro 6
card outro 8

LIST=(work/intro.mp4)
for spec in "${SCENES[@]}"; do
  IFS='|' read -r name speed title sub capstart <<< "$spec"; capstart=${capstart:-0.5}
  capout=$(python3 -c "print($capstart + 4.7)"); capend=$(python3 -c "print($capstart + 5.5)")
  [ -f "raw/$name.webm" ] || { echo "missing raw/$name.webm, skipping"; continue; }
  ffmpeg -y -loglevel error -i "raw/$name.webm" -loop 1 -framerate $FPS -i "work/cap_$name.png" -filter_complex "\
[0:v]setpts=PTS/$speed,fps=$FPS,scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=0xf4f5f7[base];\
[1:v]format=rgba,fade=t=in:st=$capstart:d=0.5:alpha=1,fade=t=out:st=$capout:d=0.6:alpha=1[cap];\
[base][cap]overlay=0:0:shortest=1:enable='lt(t,$capend)',format=yuv420p[v]" \
    -map "[v]" -r $FPS -an -c:v libx264 -preset medium -crf 18 "work/$name.mp4"
  LIST+=("work/$name.mp4")
done
LIST+=(work/outro.mp4)

n=${#LIST[@]}; inputs=(); durs=()
for f in "${LIST[@]}"; do inputs+=(-i "$f"); durs+=("$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")"); done
filter=""; prev="[0:v]"; offset=0
for ((i=1;i<n;i++)); do
  offset=$(python3 -c "print(round($offset + ${durs[$((i-1))]} - $XF, 3))")
  out="[v$i]"; [ $i -eq $((n-1)) ] && out="[vout]"
  filter+="${prev}[$i:v]xfade=transition=fade:duration=$XF:offset=$offset$out;"
  prev="[v$i]"
done
filter=${filter%;}
ffmpeg -y -loglevel error "${inputs[@]}" -filter_complex "$filter" -map "[vout]" -r $FPS -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p -movflags +faststart "$OUT_DIR/smartsearch-demo.mp4"
ffmpeg -y -loglevel error -i "$OUT_DIR/smartsearch-demo.mp4" -vf scale=1280:720 -c:v libx264 -preset slow -crf 23 -pix_fmt yuv420p -movflags +faststart "$OUT_DIR/smartsearch-demo-720p.mp4"
ffmpeg -y -loglevel error -ss 6 -t 20 -i "$OUT_DIR/smartsearch-demo.mp4" -vf "fps=10,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" "$OUT_DIR/smartsearch-demo-preview.gif" || true
ls -la "$OUT_DIR"; printf 'duration %ss\n' "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT_DIR/smartsearch-demo.mp4")"
