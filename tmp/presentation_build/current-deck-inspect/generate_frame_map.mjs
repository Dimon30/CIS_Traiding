import fs from "node:fs/promises";
import path from "node:path";

const root = "/Users/ml-coder/Projects/Active/CIS_Traiding/tmp/presentation_build/current-deck-inspect";
const layoutDir = path.join(root, "template-inspect/layouts");
const outputSlides = [];
const inspectLines = [];

for (let slide = 1; slide <= 14; slide += 1) {
  const file = path.join(layoutDir, `source-slide-${String(slide).padStart(2, "0")}.layout.json`);
  const layout = JSON.parse(await fs.readFile(file, "utf8"));
  inspectLines.push(JSON.stringify({ kind: "slide", id: layout.slide.aid, slide, title: "source slide" }));
  for (const element of layout.elements) {
    inspectLines.push(JSON.stringify({
      kind: element.kind === "shape" && element.text ? "textbox" : element.kind,
      id: element.aid,
      slide,
      name: element.name,
      text: element.text,
      textPreview: element.textPreview,
      bbox: element.bbox,
    }));
  }
  const allIds = layout.elements.map((element) => element.aid).filter(Boolean);
  const chromeNames = new Set(["section", "slide-title", "footer-rule", "TextBox 4", "TextBox 5"]);
  const chromeIds = layout.elements.filter((element) => chromeNames.has(element.name)).map((element) => element.aid);
  const contentIds = layout.elements.filter((element) => !chromeNames.has(element.name)).map((element) => element.aid);
  const editTargets = slide === 11
    ? [
        { sourceElementIds: chromeIds, action: "rewrite", reason: "Retain and recolor inherited slide chrome." },
        { sourceElementIds: contentIds, action: "rewrite", reason: "Clear and repurpose the inherited chart area for the requested date-level push inspector." },
        {
          action: "add",
          newPrimitiveAllowed: true,
          zone: { left: 73, top: 165, width: 1133, height: 450 },
          reason: "The user explicitly requested an interface showing whether a push fires on any selected day and which message is used.",
          mustNotOverlapInherited: true
        }
      ]
    : [{ sourceElementIds: allIds, action: "rewrite", reason: "Revise copy and palette in inherited slide elements." }];

  outputSlides.push({
    outputSlide: slide,
    sourceSlide: slide,
    narrativeRole: "content",
    reuseMode: "duplicate-slide",
    editTargets,
  });
}

await fs.writeFile(
  path.join(root, "template-frame-map.json"),
  `${JSON.stringify({ outputSlides, omittedSourceSlides: [] }, null, 2)}\n`,
  "utf8",
);
await fs.writeFile(path.join(root, "template-inspect-full.ndjson"), `${inspectLines.join("\n")}\n`, "utf8");
