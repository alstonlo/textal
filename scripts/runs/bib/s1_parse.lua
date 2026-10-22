-- A pandoc filter that keeps the Markdown free of HTML: cross-references become their text,
-- figures become their captions, tables become pipe tables (one line per cell, no spans),
-- spans and divs are unwrapped, sub- and superscripts become Unicode when every character has
-- a form (e.g. H₂O, Pd²⁺), else `_{...}` and `^{...}`. The abstract moves from the metadata to
-- the body, and heading levels never skip (sections without a title would make them).

local SUP = {
  ["0"] = "⁰", ["1"] = "¹", ["2"] = "²", ["3"] = "³", ["4"] = "⁴", ["5"] = "⁵", ["6"] = "⁶",
  ["7"] = "⁷", ["8"] = "⁸", ["9"] = "⁹", ["+"] = "⁺", ["-"] = "⁻", ["−"] = "⁻", ["("] = "⁽",
  [")"] = "⁾", ["="] = "⁼", ["n"] = "ⁿ", ["i"] = "ⁱ", [" "] = " ", [","] = ",", ["["] = "[",
  ["]"] = "]", ["–"] = "⁻",
}
local SUB = {
  ["0"] = "₀", ["1"] = "₁", ["2"] = "₂", ["3"] = "₃", ["4"] = "₄", ["5"] = "₅", ["6"] = "₆",
  ["7"] = "₇", ["8"] = "₈", ["9"] = "₉", ["+"] = "₊", ["-"] = "₋", ["−"] = "₋", ["("] = "₍",
  [")"] = "₎", ["="] = "₌", ["a"] = "ₐ", ["e"] = "ₑ", ["o"] = "ₒ", ["x"] = "ₓ", ["h"] = "ₕ",
  ["k"] = "ₖ", ["l"] = "ₗ", ["m"] = "ₘ", ["n"] = "ₙ", ["p"] = "ₚ", ["s"] = "ₛ", ["t"] = "ₜ",
  [" "] = " ", [","] = ",", ["["] = "[", ["]"] = "]",
}

local function to_unicode(inlines, map)
  local out = {}
  for _, code in utf8.codes(pandoc.utils.stringify(inlines)) do
    local c = map[utf8.char(code)]
    if not c then
      return nil
    end
    out[#out + 1] = c
  end
  return table.concat(out)
end

function Superscript(el)
  local s = to_unicode(el.content, SUP)
  return pandoc.Str(s or ("^{" .. pandoc.utils.stringify(el.content) .. "}"))
end

function Subscript(el)
  local s = to_unicode(el.content, SUB)
  return pandoc.Str(s or ("_{" .. pandoc.utils.stringify(el.content) .. "}"))
end

function Link(el)
  if el.target:sub(1, 1) == "#" then
    return el.content
  end
  el.attr = pandoc.Attr()
  return el
end

function Span(el)
  return el.content
end

function Div(el)
  return el.content
end

function Image(el)
  return {}
end

function Para(el)
  local s = pandoc.utils.stringify(el)
  if (#el.content == 0) or (s == "Click here for additional data file.") then
    return {}
  end
end

function Figure(el)
  return pandoc.Para(pandoc.utils.blocks_to_inlines(el.caption.long))
end

local function cell_rows(rows, width)
  local out = {}
  for _, row in ipairs(rows) do
    local cells = {}
    for _, cell in ipairs(row.cells) do
      local inlines = pandoc.utils.blocks_to_inlines(cell.contents, { pandoc.Str(";"), pandoc.Space() })
      inlines = pandoc.Inlines(inlines):walk({ LineBreak = function() return pandoc.Space() end })
      cells[#cells + 1] = { pandoc.Plain(inlines) }
      for _ = 2, cell.col_span do
        cells[#cells + 1] = { pandoc.Plain({}) }
      end
    end
    for _ = #cells + 1, width do
      cells[#cells + 1] = { pandoc.Plain({}) }
    end
    out[#out + 1] = cells
  end
  return out
end

function Table(el)
  local width = 0
  for _, spec in ipairs(el.colspecs) do
    width = width + 1
  end
  local rows = cell_rows(el.head.rows, width)
  for _, body in ipairs(el.bodies) do
    for _, row in ipairs(cell_rows(body.body, width)) do
      rows[#rows + 1] = row
    end
  end
  -- A pipe table needs a header row with content, else pandoc gives up on it.
  while #rows > 0 and pandoc.utils.stringify(pandoc.Div(rows[1][1] or {})) == "" and
      pandoc.utils.stringify(pandoc.Div(pandoc.List(rows[1]):map(function(c) return c[1] end))) == "" do
    table.remove(rows, 1)
  end
  local headers = table.remove(rows, 1) or {}
  local aligns, widths = {}, {}
  for i = 1, width do
    aligns[i], widths[i] = pandoc.AlignDefault, 0
  end
  local blocks = {}
  local caption = pandoc.utils.blocks_to_inlines(el.caption.long)
  if #caption > 0 then
    blocks[#blocks + 1] = pandoc.Para(caption)
  end
  blocks[#blocks + 1] = pandoc.utils.from_simple_table(pandoc.SimpleTable({}, aligns, widths, headers, rows))
  return blocks
end

function Pandoc(doc)
  local blocks = pandoc.List({})
  if doc.meta.abstract then
    blocks:insert(pandoc.Header(1, "Abstract"))
    local abstract = doc.meta.abstract
    if pandoc.utils.type(abstract) == "Inlines" then
      abstract = { pandoc.Para(abstract) }
    end
    for _, block in ipairs(abstract) do
      if not (block.t == "Header" and pandoc.utils.stringify(block):lower() == "abstract") then
        blocks:insert(block)
      end
    end
    doc.meta.abstract = nil
  end
  blocks:extend(doc.blocks)

  -- Pandoc writes these with Markdown escapes, which is not valid YAML.
  for _, key in ipairs({ "title", "author", "institute" }) do
    local value = doc.meta[key]
    if value and pandoc.utils.type(value) == "List" then
      doc.meta[key] = value:map(function(v) return pandoc.MetaString(pandoc.utils.stringify(v)) end)
    elseif value then
      doc.meta[key] = pandoc.MetaString(pandoc.utils.stringify(value))
    end
  end
  local level = 0
  for _, block in ipairs(blocks) do
    if block.t == "Header" then
      block.level = math.min(block.level, level + 1)
      level = block.level
    end
  end
  return pandoc.Pandoc(blocks, doc.meta)
end
