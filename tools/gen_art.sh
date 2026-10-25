#!/bin/bash
# 用 Codex 内置 image_gen（ChatGPT 订阅，不需要 API key）批量生成美术原图。
#
#   tools/gen_art.sh <提示词清单.tsv> <原图输出目录> [只生成这些名字...]
#
# 清单每行：名字<TAB>sprite|sheet|texture<TAB>描述（英文效果更稳定）。
# 统一画风：所有贴图都附上参考图 STYLE_REF（可为空）；清单第一行的贴图生成后也作为后续贴图的风格锚点。
# 已存在的 <名字>.png 会跳过，删掉再跑即可重画。生成完用 tools/import_art.py 整理进 content/art/。
# 环境变量：CODEX_MODEL（默认 gpt-5.6-terra）、JOBS（并行数，默认 4）、
#           STYLE_REF（参考图路径，设为空字符串则不用）、ART_STYLE（画风描述）。
# 清单旁边有同名 .style 文件时（比如 medieval.style），默认用它当画风描述且不附参考图。
set -u
LIST="$1"; OUT="$2"; shift 2
ONLY=" $* "
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STYLE_FILE="${LIST%.tsv}.style"
if [ -z "${ART_STYLE:-}" ] && [ -f "$STYLE_FILE" ]; then
  ART_STYLE="$(cat "$STYLE_FILE")"
  STYLE_REF="${STYLE_REF-}"
fi
REF="${STYLE_REF-$ROOT/docs/island-party-design/references/01-island-board.png}"
STYLE="${ART_STYLE:-2.5D miniature diorama, soft hand-painted with fine detail, warm top-left lighting, the same 3/4 top-down camera angle}"
MODEL="${CODEX_MODEL:-gpt-5.6-terra}"
mkdir -p "$OUT"
ANCHOR="$OUT/$(head -1 "$LIST" | cut -f1).png"

gen() {
  local name="$1" kind="$2" desc="$3" body refs=()
  [ -n "$REF" ] && refs+=(-i "$REF")
  [ -s "$OUT/$name.png" ] && { echo "$name 已存在，跳过"; return; }
  if [ "$kind" = texture ]; then
    body="Generate a square seamless tileable texture for a game terrain: $desc. Pure top-down orthographic view, flat even lighting with no directional shadows, no objects larger than a pebble, no horizon, no border, no text. Style: $STYLE (seen straight from above for this texture). The texture must tile seamlessly on all four edges."
  else
    [ -s "$ANCHOR" ] && [ "$OUT/$name.png" != "$ANCHOR" ] && refs+=(-i "$ANCHOR")
    body="Generate a game asset: $desc. Style: $STYLE. If reference images are attached, match their style exactly (style references only, do not copy their content). Centered and fully in frame with some empty margin, a soft contact shadow under the object. Transparent background with real alpha, no ground tile or grass base under it (unless described), no text, no letters, no characters, no watermark. Square image."
  fi
  local prompt="Use your built-in image_gen tool exactly once. Do not run shell commands.
$body
When done, reply with only the absolute file path of the generated image."
  local path try
  # Codex 偶尔会报一个它没真正写出的路径，失败就再试一次
  for try in 1 2; do
    path=$(echo "$prompt" | codex exec -m "$MODEL" -c model_reasoning_effort=low --enable image_generation \
      -s read-only --skip-git-repo-check ${refs[@]+"${refs[@]}"} - 2>"$OUT/log_$name.txt" \
      | grep -o '/[^ ]*generated_images/[^ ]*\.png' | tail -1)
    if [ -n "$path" ] && [ -f "$path" ]; then cp "$path" "$OUT/$name.png"; echo "$name ✓"; return; fi
  done
  echo "$name 失败，见 $OUT/log_$name.txt"
}
export -f gen
export OUT REF MODEL ANCHOR STYLE

# 先生成风格锚点，再并行生成其余
first=1
while IFS=$'\t' read -r name kind desc; do
  [ -z "$name" ] && continue
  [ "$ONLY" != "  " ] && [[ "$ONLY" != *" $name "* ]] && continue
  if [ $first = 1 ]; then gen "$name" "$kind" "$desc" >&2; first=0; continue; fi
  printf '%s\t%s\t%s\0' "$name" "$kind" "$desc"
done < "$LIST" | xargs -0 -n1 -P "${JOBS:-4}" bash -c 'IFS=$'"'"'\t'"'"' read -r n k d <<< "$1"; gen "$n" "$k" "$d"' _
