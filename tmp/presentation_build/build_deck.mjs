import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT = "/Users/ml-coder/Projects/Active/CIS_Traiding/tmp/presentation_build/transfer-trigger-model.pptx";
const PREVIEW = "/Users/ml-coder/Projects/Active/CIS_Traiding/tmp/presentation_build/rendered";
const W = 1440;
const H = 810;
const C = {
  bg: "#F3F2F7",
  orange: "#FA581B",
  peach: "#FD9066",
  pale: "#E6E5EB",
  black: "#090909",
  gray: "#6B6B70",
  mid: "#A4A4AA",
  white: "#FFFFFF",
  green: "#59B98F",
};
const FONT = "Arial";

function rect(slide, x, y, w, h, fill, radius = 18, lineFill = "none", lineWidth = 0) {
  return slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
    borderRadius: radius ? "rounded-xl" : undefined,
  });
}

function textBox(slide, x, y, w, h, text, size = 28, color = C.black, bold = false, align = "left", valign = "top") {
  const s = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  s.text = text;
  s.text.style = { fontFamily: FONT, fontSize: size, color, bold, alignment: align, verticalAlignment: valign };
  return s;
}

function circle(slide, x, y, d, fill, lineFill = "none", lineWidth = 0) {
  return slide.shapes.add({
    geometry: "ellipse",
    position: { left: x, top: y, width: d, height: d },
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
  });
}

function line(slide, x, y, w, h, color = C.pale, width = 2) {
  return slide.shapes.add({
    geometry: "line",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: color, width },
  });
}

function base(slide, n, section) {
  slide.background.fill = C.bg;
  textBox(slide, 64, 34, 260, 28, section.toUpperCase(), 14, C.gray, true);
  rect(slide, 64, 748, 42, 42, n === 1 ? C.black : C.orange, 10);
  textBox(slide, 64, 749, 42, 39, String(n).padStart(2, "0"), 15, C.white, true, "center", "middle");
}

function title(slide, value, color = C.black, y = 72, size = 48) {
  return textBox(slide, 64, y, 1312, 72, value, size, color, false);
}

function addList(slide, x, y, w, items, color = C.black, size = 24, gap = 62, accent = C.orange) {
  items.forEach((item, i) => {
    circle(slide, x, y + i * gap + 9, 12, accent);
    textBox(slide, x + 28, y + i * gap, w - 28, gap - 4, item, size, color, false);
  });
}

const p = Presentation.create({ slideSize: { width: W, height: H } });

// 1. Cover
{
  const s = p.slides.add();
  s.background.fill = C.bg;
  rect(s, 34, 30, 1372, 746, C.orange, 36);
  circle(s, 1030, -120, 620, C.peach);
  circle(s, 1120, 430, 520, "#FF9D79");
  textBox(s, 92, 82, 1120, 62, "ПРОДУКТОВАЯ ГИПОТЕЗА", 18, C.white, true);
  textBox(s, 92, 166, 1120, 205, "Выгодный момент\nдля перевода", 76, C.white, false);
  textBox(s, 96, 420, 920, 88, "Триггерная модель для редких валютных переводов", 30, C.white, false);
  rect(s, 92, 683, 50, 50, C.black, 12);
  textBox(s, 92, 684, 50, 46, "01", 16, C.white, true, "center", "middle");
  textBox(s, 1160, 690, 168, 30, "КОНЦЕПТ • 2026", 15, C.white, true, "right");
}

// 2. Customer portrait
{
  const s = p.slides.add(); base(s, 2, "Клиент");
  title(s, "Клиент переводит редко — и ценит уместность");
  textBox(s, 72, 178, 360, 220, "01", 190, C.pale, false);
  textBox(s, 88, 208, 330, 54, "Портрет", 30, C.orange, true);
  textBox(s, 88, 280, 350, 170, "Делает валютный перевод примерно 1–2 раза в месяц — плюс ситуативно перед праздниками.", 31, C.black, false);
  line(s, 500, 175, 0, 490, C.pale, 3);
  textBox(s, 570, 192, 710, 50, "Что важно в момент решения", 27, C.gray, false);
  addList(s, 570, 286, 700, [
    "Понятная практическая выгода — без лишнего шума",
    "Доверие к банку и прозрачность причины рекомендации",
    "Свобода проигнорировать сигнал без давления",
    "Релевантность конкретной валюте и привычному каналу",
  ], C.black, 26, 82);
}

// 3. Opportunity
{
  const s = p.slides.add(); base(s, 3, "Возможность");
  title(s, "Один перевод — две стороны ценности");
  rect(s, 70, 192, 590, 420, C.white, 24);
  textBox(s, 106, 226, 500, 38, "КЛИЕНТ", 16, C.orange, true);
  textBox(s, 106, 292, 500, 84, "Поймать выгодный момент", 40, C.black, false);
  textBox(s, 106, 410, 490, 120, "Получить уместную подсказку тогда, когда экономический смысл выше обычного.", 27, C.gray, false);
  rect(s, 780, 192, 590, 420, C.black, 24);
  textBox(s, 816, 226, 500, 38, "БАНК", 16, C.peach, true);
  textBox(s, 816, 292, 500, 84, "Сохранить перевод внутри", 40, C.white, false);
  textBox(s, 816, 410, 490, 120, "Увеличить вероятность, что операция пройдет через банковский валютный канал.", 27, C.white, false);
  rect(s, 642, 335, 156, 74, C.orange, 22);
  textBox(s, 642, 347, 156, 48, "WIN–WIN", 22, C.white, true, "center", "middle");
}

// 4. Trust constraint
{
  const s = p.slides.add(); base(s, 4, "Принцип");
  title(s, "Коммуникация должна быть редкой по дизайну");
  textBox(s, 72, 178, 450, 250, "НЕ\nУСТАТЬ", 94, C.orange, true);
  textBox(s, 72, 472, 430, 94, "Лояльность и доверие — ограничение модели, а не побочный KPI.", 27, C.black, false);
  line(s, 542, 184, 0, 438, C.pale, 3);
  const ys = [208, 348, 488];
  const nums = ["01", "02", "03"];
  const heads = ["Только объяснимая выгода", "Контроль частоты", "Спокойная формулировка"];
  const desc = ["Пуш отправляется, когда сигнал можно кратко и честно объяснить.", "Не реже 1–2 раз в месяц, но не чаще 1–2 раз в неделю.", "Без срочности, давления и обещаний гарантированного результата."];
  ys.forEach((y,i)=>{
    textBox(s, 600, y, 72, 44, nums[i], 22, C.orange, true);
    textBox(s, 700, y, 590, 38, heads[i], 29, C.black, true);
    textBox(s, 700, y+46, 590, 60, desc[i], 21, C.gray, false);
  });
}

// 5. Experiment design
{
  const s = p.slides.add(); base(s, 5, "Эксперимент");
  title(s, "Тестируем не одну модель, а пространство настроек");
  const labels = ["Горизонт", "Порог выгоды", "Окно расчета", "Портрет клиента", "Тихий месяц", "Канал пуша"];
  const sub = ["на сколько дней вперед", "минимальный эффект", "история для оценки", "сегмент и привычки", "fallback-поведение", "push / in-app"];
  labels.forEach((v,i)=>{
    const col = i%3; const row = Math.floor(i/3);
    const x = 72 + col*444; const y = 202 + row*204;
    rect(s, x, y, 402, 160, i===1 ? C.orange : C.white, 22);
    textBox(s, x+24, y+20, 52, 34, String(i+1).padStart(2,"0"), 17, i===1?C.white:C.orange, true);
    textBox(s, x+24, y+66, 340, 38, v, 28, i===1?C.white:C.black, true);
    textBox(s, x+24, y+111, 340, 30, sub[i], 18, i===1?C.white:C.gray, false);
  });
  textBox(s, 72, 640, 1260, 48, "Переменные закрепляем по очереди — чтобы понять вклад каждой настройки и устойчивость результата.", 24, C.black, false);
}

// 6. Decision rule
{
  const s = p.slides.add(); base(s, 6, "Критерий");
  title(s, "Побеждает модель, которая лучше случайного дня");
  textBox(s, 82, 178, 340, 250, "A/B", 150, C.pale, true);
  textBox(s, 82, 430, 380, 90, "Сигнал сравниваем с отправкой в случайный день.", 27, C.black, false);
  line(s, 500, 180, 0, 442, C.pale, 3);
  textBox(s, 562, 195, 730, 40, "Правило отбора", 28, C.gray, false);
  rect(s, 562, 274, 730, 94, C.black, 20);
  textBox(s, 592, 292, 670, 55, "Инкрементальная ценность > baseline", 30, C.white, true, "center", "middle");
  textBox(s, 562, 420, 720, 36, "Частотный коридор", 25, C.orange, true);
  textBox(s, 562, 476, 335, 98, "Нижняя граница\n1–2 раза в месяц", 29, C.black, true);
  textBox(s, 930, 476, 360, 98, "Верхняя граница\n1–2 раза в неделю", 29, C.black, true);
  line(s, 905, 476, 0, 95, C.pale, 2);
  textBox(s, 562, 600, 720, 36, "Если сигналов нет — работает заранее заданное поведение «тихого месяца».", 21, C.gray, false);
}

// 7. Currency-channel hypothesis
{
  const s = p.slides.add(); base(s, 7, "Каналы");
  title(s, "Параметры могут не совпасть между валютными каналами");
  const channels = ["Канал A", "Канал B", "Канал C"];
  const notes = ["свой горизонт и порог", "свое окно и частота", "свой сегмент и копирайт"];
  channels.forEach((v,i)=>{
    const x=72+i*444;
    textBox(s, x, 188, 360, 110, String(i+1).padStart(2,"0"), 112, C.pale, false);
    textBox(s, x+18, 256, 350, 46, v, 31, C.orange, true);
    line(s, x+18, 322, 350, 0, C.pale, 2);
    textBox(s, x+18, 354, 350, 90, notes[i], 28, C.black, false);
    textBox(s, x+18, 478, 350, 106, "Проверяем эффект отдельно, затем сравниваем переносимость настроек.", 22, C.gray, false);
  });
  rect(s, 72, 638, 1260, 58, C.orange, 16);
  textBox(s, 96, 648, 1212, 38, "Гипотеза: единый набор параметров проще, но channel-specific настройка может дать больше ценности.", 22, C.white, true, "center", "middle");
}

// 8. Signal to message
{
  const s = p.slides.add(); base(s, 8, "Сообщения");
  title(s, "Лучшие параметры превращаем в точные формулировки");
  const rows = [
    ["Выгода + привычный канал", "Сегодня условия выглядят выгоднее обычного. Проверьте курс перед переводом."],
    ["Выгода + праздник", "Если планировали перевод к праздникам, сегодня стоит проверить условия."],
    ["Слабый сигнал + тихий месяц", "Пуш не отправляем: сохраняем тишину и ждем объяснимого повода."],
  ];
  rows.forEach((r,i)=>{
    const y=198+i*150;
    textBox(s, 76, y, 330, 92, r[0], 25, i===2?C.gray:C.orange, true);
    rect(s, 440, y-10, 852, 116, i===2?C.pale:(i===1?C.orange:C.black), 24);
    textBox(s, 476, y+14, 780, 72, r[1], 24, i===2?C.gray:C.white, false, "left", "middle");
  });
  textBox(s, 76, 674, 1180, 36, "Формулировка — часть эксперимента: измеряем не только момент, но и способ объяснения.", 22, C.gray, false);
}

// 9. Inspector UI
{
  const s = p.slides.add(); base(s, 9, "Интерфейс");
  title(s, "Любой день можно проверить до запуска");
  rect(s, 70, 170, 1300, 516, C.white, 26);
  textBox(s, 104, 202, 300, 28, "TRIGGER INSPECTOR", 15, C.gray, true);
  textBox(s, 104, 250, 360, 26, "Дата", 16, C.gray, true);
  rect(s, 104, 286, 360, 58, C.bg, 14);
  textBox(s, 128, 300, 310, 34, "18 декабря 2026", 21, C.black, false);
  textBox(s, 104, 382, 360, 26, "Валютный канал", 16, C.gray, true);
  rect(s, 104, 418, 360, 58, C.bg, 14);
  textBox(s, 128, 432, 310, 34, "Канал B", 21, C.black, false);
  rect(s, 104, 530, 360, 62, C.orange, 16);
  textBox(s, 104, 544, 360, 34, "Проверить день", 22, C.white, true, "center", "middle");
  line(s, 520, 210, 0, 414, C.pale, 2);
  textBox(s, 580, 222, 200, 26, "РЕЗУЛЬТАТ", 15, C.gray, true);
  rect(s, 580, 266, 704, 82, C.black, 20);
  circle(s, 608, 290, 30, C.green);
  textBox(s, 652, 280, 590, 48, "Пуш будет отправлен", 27, C.white, true, "left", "middle");
  textBox(s, 580, 390, 200, 26, "СООБЩЕНИЕ", 15, C.gray, true);
  rect(s, 580, 430, 704, 142, C.bg, 22);
  textBox(s, 616, 458, 632, 88, "Если планировали перевод к праздникам, сегодня стоит проверить условия.", 26, C.black, false, "left", "middle");
  textBox(s, 580, 604, 704, 32, "Причина: порог выгоды пройден • частотный лимит соблюден", 18, C.gray, false);
}

// 10. Team and decision
{
  const s = p.slides.add(); base(s, 10, "Команда");
  title(s, "Команда отвечает за весь цикл — от сигнала до доверия");
  const roles = [
    ["Product", "цель, приоритеты, дизайн эксперимента"],
    ["Data Science", "модель, признаки, backtest, uplift"],
    ["Analytics", "baseline, метрики, дизайн измерения"],
    ["CRM / Copy", "каналы, частота, тексты сообщений"],
    ["Engineering", "пайплайн, интеграции, интерфейс"],
    ["Risk / Legal", "правила, прозрачность, контроль"],
  ];
  roles.forEach((r,i)=>{
    const col=i%3; const row=Math.floor(i/3); const x=72+col*444; const y=190+row*160;
    textBox(s, x, y, 72, 34, String(i+1).padStart(2,"0"), 17, C.orange, true);
    textBox(s, x+74, y, 315, 38, r[0], 28, C.black, true);
    textBox(s, x+74, y+48, 320, 64, r[1], 20, C.gray, false);
  });
  rect(s, 72, 558, 1260, 112, C.orange, 24);
  textBox(s, 106, 578, 200, 28, "СЛЕДУЮЩИЙ ШАГ", 15, C.white, true);
  textBox(s, 106, 612, 1170, 42, "Утвердить набор валютных каналов, baseline и владельцев ролей — затем запускать backtest.", 27, C.white, true);
}

await fs.mkdir(PREVIEW, { recursive: true });
for (const [i, slide] of p.slides.items.entries()) {
  const n = String(i + 1).padStart(2, "0");
  const png = await p.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(`${PREVIEW}/slide-${n}.png`, new Uint8Array(await png.arrayBuffer()));
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(`${PREVIEW}/slide-${n}.layout.json`, await layout.text());
}
const montage = await p.export({ format: "webp", montage: true, scale: 1 });
await fs.writeFile(`${PREVIEW}/montage.webp`, new Uint8Array(await montage.arrayBuffer()));
const pptx = await PresentationFile.exportPptx(p);
await pptx.save(OUT);
console.log(OUT);
