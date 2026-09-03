import fs from "node:fs/promises";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const INPUT = "/Users/ml-coder/Projects/Active/CIS_Traiding/tmp/presentation_build/current-deck-inspect/template-starter.pptx";
const OUTPUT = "/Users/ml-coder/Projects/Active/CIS_Traiding/output/pdf/CIS_Trading_trigger_model_ITMO.pptx";
const RENDER = "/Users/ml-coder/Projects/Active/CIS_Traiding/tmp/presentation_build/current-deck-inspect/final-render";
const C = {
  bg: "#F3F2F7",
  orange: "#FA581B",
  peach: "#FD9066",
  pale: "#E6E5EB",
  black: "#090909",
  gray: "#6B6B70",
  soft: "#F8E4DD",
  white: "#FFFFFF",
  green: "#59B98F",
};

const deck = await PresentationFile.importPptx(await FileBlob.load(INPUT));

function shapeByName(slide, name) {
  return slide.shapes.items.find((shape) => shape.name === name);
}

function setText(slide, name, value, color) {
  const shape = shapeByName(slide, name);
  if (!shape) throw new Error(`Missing shape ${name}`);
  shape.text = value;
  if (color) shape.text.style = { color };
  return shape;
}

function colorText(slide, names, color) {
  for (const name of names) {
    const shape = shapeByName(slide, name);
    if (shape) shape.text.style = { color };
  }
}

function setAccentBullet(slide, name, value, accent) {
  const shape = shapeByName(slide, name);
  if (!shape) throw new Error(`Missing shape ${name}`);
  shape.text = [[
    { run: "•", textStyle: { color: accent } },
    { run: `  ${value}`, textStyle: { color: C.black } },
  ]];
  return shape;
}

function addShape(slide, geometry, name, x, y, w, h, fill, radius = 0, lineFill = "none", lineWidth = 0) {
  return slide.shapes.add({
    geometry,
    name,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
    ...(radius ? { borderRadius: radius } : {}),
  });
}

function addText(slide, name, x, y, w, h, value, size, color, bold = false, align = "left", valign = "top") {
  const shape = addShape(slide, "textbox", name, x, y, w, h, "none");
  shape.text = value;
  shape.text.style = {
    fontFamily: "Arial",
    fontSize: size,
    color,
    bold,
    alignment: align,
    verticalAlignment: valign,
    autoFit: "shrinkText",
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}

function applyChrome(slide, number) {
  slide.background.fill = C.bg;
  const section = shapeByName(slide, "section");
  const title = shapeByName(slide, "slide-title");
  const footer = shapeByName(slide, "TextBox 4");
  const page = shapeByName(slide, "TextBox 5");
  const rule = shapeByName(slide, "footer-rule");
  if (section) section.text.color = C.orange;
  if (title) title.text.color = C.black;
  if (footer) { footer.text = "CIS TRADING  /  ТРИГГЕРНАЯ МОДЕЛЬ"; footer.text.color = C.gray; }
  if (page) { page.text = String(number).padStart(2, "0"); page.text.color = C.gray; }
  if (rule) rule.line = { style: "solid", fill: C.pale, width: 1 };
}

// Cover: preserve the original composition and replace its accent system.
{
  const s = deck.slides.items[0];
  s.background.fill = C.bg;
  const r1 = shapeByName(s, "Прямоугольник 1"); if (r1) r1.fill = C.orange;
  const r2 = shapeByName(s, "Прямоугольник 2"); if (r2) r2.fill = C.peach;
  const o1 = shapeByName(s, "Овал 8"); if (o1) o1.fill = C.orange;
  const o2 = shapeByName(s, "Овал 9"); if (o2) o2.fill = C.peach;
  setText(s, "TextBox 4", "Когда выгодно\nперевести деньги");
  setText(s, "TextBox 5", "Триггерная модель: от сигнала к уместному пушу", C.gray);
  setText(s, "TextBox 7", "RUB → TJS  ·  03.09.2026", C.gray);
  colorText(s, ["TextBox 3", "TextBox 10"], C.orange);
}

for (let i = 1; i < deck.slides.items.length; i += 1) applyChrome(deck.slides.items[i], i + 1);

// 2. Customer portrait + business value.
{
  const s = deck.slides.items[1];
  setText(s, "section", "КЛИЕНТ");
  setText(s, "slide-title", "Редкий перевод требует точного момента");
  setText(s, "TextBox 6", "«Перевести сегодня — или подождать?»");
  setText(s, "TextBox 7", "Клиент переводит примерно 1–2 раза в месяц — плюс ситуативно перед праздниками. Постоянно следить за рынком он не хочет.");
  setText(s, "TextBox 9", "Общая выгода", C.orange);
  setText(s, "TextBox 10", "Клиент получает уместный момент, а банк сохраняет валютный перевод внутри своего канала.");
  setText(s, "TextBox 11", "Поэтому уместность важнее охвата.", C.orange);
  const card = shapeByName(s, "Скругленный прямоугольник 8"); if (card) card.fill = C.soft;
}

// 3. Core question.
{
  const s = deck.slides.items[2];
  setText(s, "section", "ПОВЕДЕНИЕ");
  setText(s, "slide-title", "Ищем редкие дни с объяснимой выгодой");
  setText(s, "TextBox 6", "Система отвечает на один вопрос:");
  setText(s, "TextBox 7", "Есть ли сегодня достаточно сильный повод предложить перевод?");
  setText(s, "TextBox 9", "СЕГОДНЯ", C.orange);
  setText(s, "TextBox 10", "оценка только по прошлому и настоящему");
  setText(s, "TextBox 11", "ГОРИЗОНТ", C.peach);
  setText(s, "TextBox 12", "сколько дней вперед учитываем в решении");
  setText(s, "TextBox 13", "ТИШИНА", C.black);
  setText(s, "TextBox 14", "слабый сигнал не превращаем в пуш ради частоты");
}

// 4. Trust and cadence contract.
{
  const s = deck.slides.items[3];
  setText(s, "section", "ПРОДУКТОВЫЙ КОНТРАКТ");
  setText(s, "slide-title", "Лояльность задаёт границы частоты");
  const pairs = [
    ["TextBox 6", "1–2", "TextBox 7", "пуша в месяц — не реже"],
    ["TextBox 9", "1–2", "TextBox 10", "пуша в неделю — не чаще"],
    ["TextBox 12", "90%", "TextBox 13", "минимальная доля правдивых пушей"],
    ["TextBox 15", "4", "TextBox 16", "дня cooldown после отправки"],
    ["TextBox 18", "0", "TextBox 19", "давления и ложной срочности"],
  ];
  pairs.forEach((p, i) => {
    setText(s, p[0], p[1], i % 2 ? C.peach : C.orange);
    setText(s, p[2], p[3]);
  });
  setText(s, "TextBox 20", "Редкий правдивый пуш лучше частой коммуникации без достаточного повода.");
}

// 5. Model feature space.
{
  const s = deck.slides.items[4];
  setText(s, "section", "МОДЕЛЬ");
  setText(s, "slide-title", "Тестируем закреплённые параметры модели");
  const labels = [
    ["TextBox 12", "Горизонт"],
    ["TextBox 14", "Порог\nвыгоды"],
    ["TextBox 16", "Окно\nрасчёта"],
    ["TextBox 18", "Портрет\nклиента"],
    ["TextBox 20", "Тихий\nмесяц"],
    ["TextBox 22", "Канал\nпуша"],
  ];
  labels.forEach(([name, value], i) => setText(s, name, value, i === 5 ? C.white : C.black));
  setText(s, "TextBox 23", "Переменные закрепляем по очереди и в комбинациях.", C.orange);
  setText(s, "TextBox 24", "Так отделяем вклад настройки от случайности и находим устойчивую policy отправки.");
  const cards = ["Скругленный прямоугольник 11","Скругленный прямоугольник 13","Скругленный прямоугольник 15","Скругленный прямоугольник 17","Скругленный прямоугольник 19"];
  cards.forEach((name) => { const sh = shapeByName(s, name); if (sh) sh.fill = C.soft; });
  const last = shapeByName(s, "Скругленный прямоугольник 21"); if (last) last.fill = C.black;
  for (const sh of s.shapes.items) if ((sh.name || "").includes("соединительная линия")) sh.line = { style: "solid", fill: C.orange, width: 2 };
}

// 6. Preserve data evidence, recolor key metrics.
{
  const s = deck.slides.items[5];
  setText(s, "section", "ДАННЫЕ");
  setText(s, "slide-title", "10 лет данных → 2 462 полные метки");
  colorText(s, ["TextBox 6", "TextBox 10"], C.orange);
  colorText(s, ["TextBox 8"], C.peach);
}

// 7. Experiment plan.
{
  const s = deck.slides.items[6];
  setText(s, "section", "ПЛАН ТЕСТА");
  setText(s, "slide-title", "Перебираем параметры по одному и вместе");
  const items = [
    "Зафиксировать горизонт и окно расчёта",
    "Перебрать порог экономической выгоды",
    "Разделить портреты клиентов",
    "Задать поведение в тихий месяц",
    "Сравнить push и in-app каналы",
    "Проверить валютные каналы отдельно",
  ];
  ["TextBox 9","TextBox 12","TextBox 15","TextBox 18","TextBox 21","TextBox 24"].forEach((name, i) => setText(s, name, items[i]));
  ["TextBox 8","TextBox 11","TextBox 14","TextBox 17","TextBox 20","TextBox 23"].forEach((name, i) => setText(s, name, "✓", i % 2 ? C.peach : C.orange));
  s.shapes.items.filter((sh) => (sh.name || "").startsWith("Овал")).forEach((sh, i) => { sh.fill = i % 2 ? C.peach : C.orange; });
  const checklistLine = shapeByName(s, "Прямая соединительная линия 6"); if (checklistLine) checklistLine.line = { style: "solid", fill: C.pale, width: 2 };
}

// 8. Baseline and temporal validation.
{
  const s = deck.slides.items[7];
  setText(s, "section", "КРИТЕРИЙ");
  setText(s, "slide-title", "Baseline: случайный день без утечки будущего");
  setText(s, "TextBox 25", "Побеждает вариант, который лучше случайного дня. Threshold выбираем только на validation.");
  colorText(s, ["TextBox 6", "TextBox 8"], C.orange);
  colorText(s, ["TextBox 10"], C.peach);
  const trainBar = shapeByName(s, "Прямоугольник 13"); if (trainBar) trainBar.fill = C.orange;
  const validationBar = shapeByName(s, "Прямоугольник 17"); if (validationBar) validationBar.fill = C.peach;
  const testBar = shapeByName(s, "Прямоугольник 21"); if (testBar) testBar.fill = C.black;
  colorText(s, ["TextBox 14"], C.orange);
  colorText(s, ["TextBox 18"], C.peach);
}

// 9. Current evidence.
{
  const s = deck.slides.items[8];
  setText(s, "section", "ТЕКУЩИЙ BASELINE");
  setText(s, "slide-title", "Сигнал есть, но 90% precision пока нет");
  colorText(s, ["TextBox 7", "TextBox 19"], C.orange);
  colorText(s, ["TextBox 9", "TextBox 13", "TextBox 21"], C.peach);
  colorText(s, ["TextBox 6", "TextBox 12"], C.orange);
  const precisionBar = shapeByName(s, "Прямоугольник 16"); if (precisionBar) precisionBar.fill = C.orange;
}

// 10. Bank value constrained by trust.
{
  const s = deck.slides.items[9];
  setText(s, "section", "БЕНЕФИЦИАР И РИСК");
  setText(s, "slide-title", "Выгода банка не должна стоить доверия клиента");
  setText(s, "TextBox 7", "ЦЕННОСТЬ ДЛЯ БАНКА", C.orange);
  setText(s, "TextBox 8", "Перевод остаётся в канале");
  setText(s, "TextBox 9", "Уместный сигнал повышает вероятность, что клиент проведёт валютный перевод через банк.");
  setText(s, "TextBox 10", "Экономический эффект должен быть инкрементальным.", C.orange);
  setText(s, "TextBox 12", "ОГРАНИЧЕНИЕ", C.peach);
  setText(s, "TextBox 13", "Лишний пуш разрушает доверие", C.white);
  setText(s, "TextBox 14", "Поэтому частота ограничена, причина прозрачна, а слабый сигнал остаётся без коммуникации.", C.white);
  const cards = s.shapes.items.filter((sh) => (sh.name || "").includes("Скругленный прямоугольник"));
  if (cards[0]) cards[0].fill = C.soft;
  if (cards[1]) cards[1].fill = C.black;
}

// 11. Daily push inspector interface.
{
  const s = deck.slides.items[10];
  setText(s, "section", "ИНТЕРФЕЙС");
  setText(s, "slide-title", "Инспектор показывает пуш и сообщение на любой день");
  const chrome = new Set(["section", "slide-title", "footer-rule", "TextBox 4", "TextBox 5"]);
  for (const sh of s.shapes.items) {
    if (chrome.has(sh.name)) continue;
    if (sh.text) sh.text = "";
    sh.fill = "none";
    sh.line = { style: "solid", fill: "none", width: 0 };
  }
  const inspectorShell = addShape(s, "roundRect", "inspector-shell", 74, 170, 1132, 440, C.white, 22);
  inspectorShell.text = "TRIGGER INSPECTOR";
  inspectorShell.text.style = { fontFamily: "Arial", fontSize: 15, color: C.gray, bold: true, verticalAlignment: "top", insets: { top: 25, right: 30, bottom: 0, left: 30 } };
  addText(s, "date-label", 104, 240, 120, 22, "Дата", 15, C.gray, true);
  addShape(s, "roundRect", "date-field", 104, 270, 330, 52, C.bg, 12);
  addText(s, "date-value", 124, 282, 292, 28, "18 декабря 2026", 20, C.black);
  addText(s, "channel-label", 104, 354, 180, 22, "Валютный канал", 15, C.gray, true);
  addShape(s, "roundRect", "channel-field", 104, 384, 330, 52, C.bg, 12);
  addText(s, "channel-value", 124, 396, 292, 28, "RUB → TJS", 20, C.black);
  addShape(s, "roundRect", "check-button", 104, 486, 330, 58, C.orange, 14);
  addText(s, "check-button-text", 104, 501, 330, 28, "Проверить день", 21, C.white, true, "center", "middle");
  addShape(s, "line", "ui-divider", 500, 205, 0, 348, "none", 0, C.pale, 2);
  addText(s, "result-label", 560, 215, 180, 22, "РЕЗУЛЬТАТ", 15, C.gray, true);
  const resultCard = addShape(s, "roundRect", "result-card", 560, 252, 590, 82, C.black, 18);
  resultCard.text = "Пуш будет отправлен";
  resultCard.text.style = { fontFamily: "Arial", fontSize: 25, color: C.white, bold: true, verticalAlignment: "middle", insets: { top: 0, right: 20, bottom: 0, left: 72 } };
  addShape(s, "ellipse", "status-dot", 588, 278, 28, 28, C.green);
  addText(s, "message-label", 560, 370, 180, 22, "СООБЩЕНИЕ", 15, C.gray, true);
  const messageCard = addShape(s, "roundRect", "message-card", 560, 407, 590, 108, C.bg, 16);
  messageCard.text = "Если планировали перевод к праздникам, сегодня стоит проверить условия.";
  messageCard.text.style = { fontFamily: "Arial", fontSize: 22, color: C.black, verticalAlignment: "middle", autoFit: "shrinkText", insets: { top: 16, right: 32, bottom: 16, left: 32 } };
  addText(s, "reason-code", 560, 548, 590, 28, "Причина: порог пройден · frequency cap соблюдён", 16, C.gray);
}

// 12. Channel-specific hypothesis.
{
  const s = deck.slides.items[11];
  setText(s, "section", "ВАЛЮТНЫЕ КАНАЛЫ");
  setText(s, "slide-title", "Проверяем, совпадают ли лучшие параметры");
  setText(s, "TextBox 6", "ЕДИНЫЕ ПАРАМЕТРЫ", C.orange);
  setText(s, "TextBox 8", "Один горизонт и порог для всех каналов");
  setText(s, "TextBox 10", "Проще поддерживать и объяснять");
  setText(s, "TextBox 12", "Риск потерять channel-specific эффект");
  setText(s, "TextBox 13", "CHANNEL-SPECIFIC", C.peach);
  setText(s, "TextBox 15", "Свой порог, окно и cooldown");
  setText(s, "TextBox 17", "Свой портрет клиента и частота");
  setText(s, "TextBox 19", "Свои формулировки сигнала");
  setText(s, "TextBox 20", "Отдельно: курс ЦБ не равен фактическому банковскому курсу перевода.");
}

// 13. Selection to copy system.
{
  const s = deck.slides.items[12];
  setText(s, "section", "ОТ СИГНАЛА К ТЕКСТУ");
  setText(s, "slide-title", "Лучшие параметры превращаем в тексты");
  const heads = ["Настроить горизонты", "Выбрать пороги", "Проверить частоту", "Собрать сигналы", "Написать тексты", "Собрать инспектор"];
  const subs = ["по каждому каналу", "лучше random-day baseline", "1–2/мес → 1–2/нед", "выгода / праздник / тишина", "точечно под комбинации", "день → пуш → сообщение"];
  ["TextBox 9","TextBox 14","TextBox 19","TextBox 24","TextBox 29","TextBox 33"].forEach((name, i) => setText(s, name, heads[i]));
  ["TextBox 10","TextBox 15","TextBox 20","TextBox 25","TextBox 30","TextBox 34"].forEach((name, i) => setText(s, name, subs[i]));
  ["TextBox 7","TextBox 12","TextBox 17","TextBox 22","TextBox 27","TextBox 31"].forEach((name, i) => setText(s, name, String(i+1).padStart(2,"0"), i%2?C.peach:C.orange));
  ["Прямая соединительная линия 8","Прямая соединительная линия 13","Прямая соединительная линия 18","Прямая соединительная линия 23","Прямая соединительная линия 28","Прямая соединительная линия 32"].forEach((name, i) => {
    const sh = shapeByName(s, name); if (sh) sh.line = { style: "solid", fill: i % 2 ? C.peach : C.orange, width: 5 };
  });
  setText(s, "TextBox 36", "GATE", C.peach);
  setText(s, "TextBox 37", "message lift > 1  ·  лучше случайного дня  ·  частота внутри коридора", C.white);
  const gate = s.shapes.items.find((sh) => (sh.name || "").includes("Скругленный прямоугольник")); if (gate) gate.fill = C.black;
}

// 14. Team and next decision.
{
  const s = deck.slides.items[13];
  setText(s, "section", "КОМАНДА");
  setText(s, "slide-title", "Команда закрывает модель, продукт и доверие");
  colorText(s, ["TextBox 7", "TextBox 11", "TextBox 15"], C.orange);
  const next = setText(s, "TextBox 18", "Следующий шаг: утвердить каналы и владельцев — затем запустить backtest.", C.white);
  next.text.fontSize = 25;
  const banner = s.shapes.items.find((sh) => (sh.name || "").includes("Скругленный прямоугольник")); if (banner) banner.fill = C.orange;
}

for (const slide of deck.slides.items) {
  slide.speakerNotes.textFrame.setText("[Sources]\n- User brief in this Codex task.\n- Visual palette reference: AI Product Hack 2026 - интро.pptx.pdf (user-provided).\n- Project metrics retained from CIS_Traiding_status_ITMO.pptx (user-provided).\n[/Sources]");
}

await fs.mkdir(RENDER, { recursive: true });
await fs.mkdir("/Users/ml-coder/Projects/Active/CIS_Traiding/output/pdf", { recursive: true });
for (const [index, slide] of deck.slides.items.entries()) {
  const n = String(index + 1).padStart(2, "0");
  const png = await deck.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(`${RENDER}/slide-${n}.png`, new Uint8Array(await png.arrayBuffer()));
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(`${RENDER}/slide-${n}.layout.json`, await layout.text());
}
const montage = await deck.export({ format: "webp", montage: true, scale: 1 });
await fs.writeFile(`${RENDER}/montage.webp`, new Uint8Array(await montage.arrayBuffer()));
const pptx = await PresentationFile.exportPptx(deck);
await pptx.save(OUTPUT);
console.log(OUTPUT);
