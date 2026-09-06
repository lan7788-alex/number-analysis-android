import os
import re
from itertools import combinations

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.utils import platform

ALL_NUMBERS = [f"{i:03d}" for i in range(1000)]
SIZE_SHAPES = ["大大大", "大大小", "大小大", "大小小", "小大大", "小大小", "小小大", "小小小"]
PARITY_SHAPES = ["奇奇奇", "奇奇偶", "奇偶奇", "奇偶偶", "偶奇奇", "偶奇偶", "偶偶奇", "偶偶偶"]
POSITION_MAP = {"百十": [0, 1], "百个": [0, 2], "十个": [1, 2]}


def find_chinese_font():
    """优先使用项目内置中文字体；没有时自动使用 Android 系统中文字体。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "fonts", "chinese.ttf"),
        os.path.join(base_dir, "fonts", "chinese.otf"),
        "/system/fonts/NotoSansCJK-Regular.ttc",
        "/system/fonts/NotoSansCJKsc-Regular.otf",
        "/system/fonts/NotoSansSC-Regular.otf",
        "/system/fonts/DroidSansFallback.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path

    # 不同品牌 Android 的字体文件名可能略有差异，继续自动扫描。
    system_font_dir = "/system/fonts"
    if os.path.isdir(system_font_dir):
        try:
            names = os.listdir(system_font_dir)
            priority = ("NotoSansCJK", "NotoSansSC", "DroidSansFallback", "NotoSerifCJK")
            for key in priority:
                for name in names:
                    low = name.lower()
                    if key.lower() in low and low.endswith((".ttf", ".otf", ".ttc")):
                        return os.path.join(system_font_dir, name)
        except Exception:
            pass

    return "Roboto"


CHINESE_FONT = find_chinese_font()

# 给整个 Kivy 界面统一指定中文字体：标题、按钮、下拉框、输入框、弹窗等都会生效。
if CHINESE_FONT != "Roboto":
    _font = CHINESE_FONT.replace("\\", "/")
    Builder.load_string(f"""
<Label>:
    font_name: "{_font}"
<Button>:
    font_name: "{_font}"
<Spinner>:
    font_name: "{_font}"
<TextInput>:
    font_name: "{_font}"
<Popup>:
    title_font: "{_font}"
""")

MODES = [
    "口径1取号",
    "形态取号",
    "口径1双条件全量交集",
    "口径1交集后数字形态轨",
    "交集 / 不交集",
    "A分别与多个文件交集",
    "合并去重",
    "形态筛选",
    "二同 / 三同 / 三不同",
    "两位组合命中筛选（按附件）",
    "两位组合命中筛选（000-999）",
    "数字包含 / 去除筛选",
    "三至七位拆两位组合",
    "半顺以上筛选",
]


def parse_numbers(text):
    return sorted(set(re.findall(r"(?<!\d)\d{3}(?!\d)", text or "")))


def format_txt(nums):
    nums = sorted(set(nums))
    return "\n".join(" ".join(nums[i:i + 10]) for i in range(0, len(nums), 10))



def section_text(title, nums):
    nums = sorted(set(nums))
    body = format_txt(nums) if nums else "（无）"
    return f"【{title}】{len(nums)} 注\n{body}"

def pair_section_text(title, pairs):
    pairs = sorted(set(pairs))
    body = "\n".join(" ".join(pairs[i:i+10]) for i in range(0, len(pairs), 10)) if pairs else "（无）"
    return f"【{title}】{len(pairs)}组\n{body}"

def size_shape(num):
    return "".join("大" if int(d) >= 5 else "小" for d in num)


def parity_shape(num):
    return "".join("奇" if int(d) % 2 else "偶" for d in num)


def repeat_type(num):
    n = len(set(num))
    return "三不同" if n == 3 else ("二同" if n == 2 else "三同")


def allowed_shapes(mother_shape, position_name, all_shapes):
    # 保留原逻辑，供已经核对无误的其他功能继续使用。
    pos = POSITION_MAP[position_name]
    return [s for s in all_shapes if not all(s[p] == mother_shape[p] for p in pos)]


def allowed_shapes_normal(mother_shape, position_name, all_shapes):
    """口径1正常取号：保留母号自身形态，排除指定两位均为相反属性的2个形态。"""
    pos = POSITION_MAP[position_name]
    opposite = {"大": "小", "小": "大", "奇": "偶", "偶": "奇"}
    target = {p: opposite[mother_shape[p]] for p in pos}
    return [s for s in all_shapes if not all(s[p] == target[p] for p in pos)]


def normalize_rule_text(text):
    text = (text or "").strip()
    for ch in [" ", "+", "/", "／", "，", ",", "；", ";", "：", ":"]:
        text = text.replace(ch, "")
    return text


def parse_koujing1(text):
    text = normalize_rule_text(text)
    m = re.match(r"^(\d{3})(.*)$", text)
    if not m:
        return None, "格式无法识别"
    mother, rule = m.group(1), m.group(2)
    if rule in POSITION_MAP:
        return {"mother": mother, "size_pos": rule, "parity_pos": rule, "display_rule": rule}, None
    m2 = re.fullmatch(r"大小(百十|百个|十个)奇偶(百十|百个|十个)", rule)
    if m2:
        return {
            "mother": mother,
            "size_pos": m2.group(1),
            "parity_pos": m2.group(2),
            "display_rule": f"大小{m2.group(1)} + 奇偶{m2.group(2)}",
        }, None
    return None, "取位无法识别，例如：818十个 或 888大小百十奇偶十个"


def run_koujing1(mother, size_pos, parity_pos):
    ms, mp = size_shape(mother), parity_shape(mother)
    asize = allowed_shapes(ms, size_pos, SIZE_SHAPES)
    apar = allowed_shapes(mp, parity_pos, PARITY_SHAPES)
    full = [n for n in ALL_NUMBERS if size_shape(n) in asize and parity_shape(n) in apar]
    same23 = [n for n in full if repeat_type(n) != "三不同"]
    different = [n for n in full if repeat_type(n) == "三不同"]
    return {
        "mother_size": ms,
        "mother_parity": mp,
        "allowed_size": asize,
        "allowed_parity": apar,
        "full": sorted(full),
        "same23": sorted(same23),
        "different": sorted(different),
    }


def run_koujing1_normal(mother, size_pos, parity_pos):
    """仅用于“口径1取号”菜单的正常取号逻辑。"""
    ms, mp = size_shape(mother), parity_shape(mother)
    asize = allowed_shapes_normal(ms, size_pos, SIZE_SHAPES)
    apar = allowed_shapes_normal(mp, parity_pos, PARITY_SHAPES)
    full = [n for n in ALL_NUMBERS if size_shape(n) in asize and parity_shape(n) in apar]
    same23 = [n for n in full if repeat_type(n) != "三不同"]
    different = [n for n in full if repeat_type(n) == "三不同"]
    return {
        "mother_size": ms,
        "mother_parity": mp,
        "allowed_size": asize,
        "allowed_parity": apar,
        "full": sorted(full),
        "same23": sorted(same23),
        "different": sorted(different),
    }


def parse_digit_track(text):
    s = (text or "").replace("数字", "").replace(" ", "")
    out = []
    for c in s:
        if c.isdigit() and c not in out:
            out.append(c)
    return out


def run_digit_track(base_nums, target_digits):
    buckets = {}
    for num in base_nums:
        c = sum(1 for d in target_digits if d not in num)
        buckets.setdefault(c, []).append(num)
    bc = sorted(set(buckets.get(2, [])) | set(buckets.get(3, [])))
    return buckets, bc


def classify_shape_token(token):
    if token in SIZE_SHAPES:
        return "size"
    if token in PARITY_SHAPES:
        return "parity"
    return None


def run_shape_track(base_nums, shape_tokens):
    valid = [(t, classify_shape_token(t)) for t in shape_tokens if classify_shape_token(t)]
    counts = {n: 0 for n in base_nums}
    for token, kind in valid:
        for n in base_nums:
            matched = (size_shape(n) == token) if kind == "size" else (parity_shape(n) == token)
            if not matched:
                counts[n] += 1
    buckets = {}
    for n, c in counts.items():
        buckets.setdefault(c, []).append(n)
    cd = sorted(set(buckets.get(3, [])) | set(buckets.get(4, [])))
    return valid, buckets, cd


def canonical_pair(pair):
    return "".join(sorted(pair)) if len(pair) == 2 and pair.isdigit() else None


def parse_pair_conditions(text):
    return {canonical_pair(p) for p in re.findall(r"(?<!\d)\d{2}(?!\d)", text or "") if canonical_pair(p)}


def pair_hit_count(num, pair_set):
    a, b, c = num
    pairs = [canonical_pair(a + b), canonical_pair(a + c), canonical_pair(b + c)]
    return sum(1 for p in pairs if p in pair_set)


def run_pair_filter(base_nums, pair_set, mode):
    selected, rejected = [], []
    for n in base_nums:
        h = pair_hit_count(n, pair_set)
        ok = h >= 2 if mode == "两对命中（至少2对）" else (h == 2 if mode == "恰好两对命中" else h == 3)
        (selected if ok else rejected).append(n)
    return sorted(selected), sorted(rejected)


def split_to_pairs(token):
    token = (token or "").strip()
    if not (token.isdigit() and 3 <= len(token) <= 7):
        return []
    pairs = set()
    for i, j in combinations(range(len(token)), 2):
        pairs.add(canonical_pair(token[i] + token[j]))
    return sorted(pairs)


def parse_split_inputs(text):
    return re.findall(r"(?<!\d)\d{3,7}(?!\d)", text or "")


def sequence_type(num):
    d = sorted(int(x) for x in num)
    if len(set(d)) != 3:
        return "非半顺"
    if d[1] - d[0] == 1 and d[2] - d[1] == 1:
        return "全顺"
    if d[1] - d[0] == 1 or d[2] - d[1] == 1:
        return "半顺"
    return "非半顺"


class NumberAnalysisRoot(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(8), padding=dp(8), **kwargs)
        self.loaded_files = []
        self.current_exports = {}
        self.current_view_name = None
        self.current_page = 0
        self.page_size = 100

        self.add_widget(Label(text="数字分析工具（离线版）", size_hint_y=None, height=dp(42), font_size="20sp"))
        self.mode = Spinner(text=MODES[0], values=MODES, size_hint_y=None, height=dp(48))
        self.mode.bind(text=self.on_mode_change)
        self.add_widget(self.mode)

        self.instructions = Label(text="", size_hint_y=None, height=dp(72), halign="left", valign="middle")
        self.instructions.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0], None)))
        self.add_widget(self.instructions)

        self.input1 = TextInput(multiline=True, hint_text="输入1", size_hint_y=None, height=dp(110))
        self.input2 = TextInput(multiline=True, hint_text="输入2", size_hint_y=None, height=dp(110))
        self.input3 = TextInput(multiline=True, hint_text="输入3", size_hint_y=None, height=dp(90))
        self.add_widget(self.input1)
        self.add_widget(self.input2)
        self.add_widget(self.input3)

        btnrow = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        bload = Button(text="选择TXT附件")
        bload.bind(on_release=self.open_files)
        brunar = Button(text="开始分析")
        brunar.bind(on_release=self.run_analysis)
        btnrow.add_widget(bload)
        btnrow.add_widget(brunar)
        self.add_widget(btnrow)

        self.files_label = Label(text="未选择附件", size_hint_y=None, height=dp(54), halign="left", valign="middle")
        self.files_label.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0], None)))
        self.add_widget(self.files_label)

        self.summary = TextInput(
            readonly=True,
            multiline=True,
            size_hint_y=None,
            height=dp(185),
            hint_text="分析摘要"
        )
        self.add_widget(self.summary)

        chooserow = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.result_selector = Spinner(text="选择结果", values=(), size_hint_x=0.68)
        self.result_selector.bind(text=self.on_result_selected)
        bview = Button(text="全屏查看", size_hint_x=0.32)
        bview.bind(on_release=self.open_full_result)
        chooserow.add_widget(self.result_selector)
        chooserow.add_widget(bview)
        self.add_widget(chooserow)

        self.page_label = Label(text="", size_hint_y=None, height=dp(38), halign="left", valign="middle")
        self.page_label.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0], None)))
        self.add_widget(self.page_label)

        self.result = TextInput(
            readonly=True,
            multiline=True,
            size_hint_y=None,
            height=dp(360),
            hint_text="选择结果后，这里显示完整组合（10注一行，可上下滚动）"
        )
        self.add_widget(self.result)

        exportrow1 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        bcurrent = Button(text="保存当前到下载")
        bcurrent.bind(on_release=self.export_current_to_download)
        ball = Button(text="保存全部到下载")
        ball.bind(on_release=self.export_results_to_download)
        exportrow1.add_widget(bcurrent)
        exportrow1.add_widget(ball)
        self.add_widget(exportrow1)

        exportrow2 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        bexport_app = Button(text="导出全部到App目录")
        bexport_app.bind(on_release=self.export_results)
        bclear = Button(text="清空")
        bclear.bind(on_release=self.clear_all)
        exportrow2.add_widget(bexport_app)
        exportrow2.add_widget(bclear)
        self.add_widget(exportrow2)

        self.on_mode_change(self.mode, self.mode.text)

    def on_mode_change(self, _spinner, mode):
        self.loaded_files = []
        self.files_label.text = "未选择附件"
        self.current_exports = {}
        self.current_view_name = None
        self.current_page = 0
        self.summary.text = ""
        self.result.text = ""
        self.result_selector.values = ()
        self.result_selector.text = "选择结果"
        self.page_label.text = ""
        self.input1.text = self.input2.text = self.input3.text = ""

        hints = {
            "口径1取号": ("输入口径1条件，可多行，例如：592百个\n888大小百十奇偶十个", "", ""),
            "形态取号": ("输入大小形态，可任意数量，例如：大大大、大大小、大小大", "输入奇偶形态，可任意数量，例如：奇奇奇、奇奇偶、偶奇奇", ""),
            "口径1双条件全量交集": ("条件A，例如：818十个", "条件B，例如：881十个", ""),
            "口径1交集后数字形态轨": ("母号A条件，例如：983十个", "母号B条件，例如：938十个", "第1行数字389；后续4行形态"),
            "交集 / 不交集": ("请用“选择TXT附件”选择A、B两个文件", "", ""),
            "A分别与多个文件交集": ("第一个附件为A，其余为B/C/D...", "", ""),
            "合并去重": ("选择至少2个TXT附件", "", ""),
            "形态筛选": ("输入要去掉的大小形态，可为空", "输入要去掉的奇偶形态，可为空", "选择1个基础TXT"),
            "二同 / 三同 / 三不同": ("选择1个基础TXT", "", ""),
            "两位组合命中筛选（按附件）": ("输入两位组合，如：01 03 05 06...", "模式：至少2对 / 恰好2对 / 三对全命中", "选择1个基础TXT"),
            "两位组合命中筛选（000-999）": ("输入两位组合，如：01 03 05 06...", "模式：至少2对 / 恰好2对 / 三对全命中", ""),
            "数字包含 / 去除筛选": ("输入数字，例如：8 或 368", "第1行：任意/全部；第2行：筛出/去掉", "选择1个基础TXT"),
            "三至七位拆两位组合": ("输入3-7位数字，可多组，例如：345 4567 124579", "", ""),
            "半顺以上筛选": ("选择1个基础TXT", "", ""),
        }
        a, b, c = hints[mode]
        self.instructions.text = "本次只使用当前输入和当前附件，不调用旧数据。"
        self.input1.hint_text, self.input2.hint_text, self.input3.hint_text = a, b, c

    def clear_all(self, *_):
        self.input1.text = self.input2.text = self.input3.text = ""
        self.loaded_files = []
        self.files_label.text = "未选择附件"
        self.summary.text = ""
        self.result.text = ""
        self.current_exports = {}
        self.current_view_name = None
        self.current_page = 0
        self.result_selector.values = ()
        self.result_selector.text = "选择结果"
        self.page_label.text = ""

    def open_files(self, *_):
        chooser = FileChooserListView(path=os.path.expanduser("~"), filters=["*.txt"], multiselect=True)
        box = BoxLayout(orientation="vertical")
        box.add_widget(chooser)
        row = BoxLayout(size_hint_y=None, height=dp(48))
        ok = Button(text="确定")
        cancel = Button(text="取消")
        row.add_widget(ok)
        row.add_widget(cancel)
        box.add_widget(row)
        pop = Popup(title="选择TXT附件", content=box, size_hint=(0.95, 0.9))

        def choose(*_args):
            self.loaded_files = chooser.selection[:]
            if self.loaded_files:
                self.files_label.text = "已选择：" + "、".join(os.path.basename(p) for p in self.loaded_files)
            else:
                self.files_label.text = "未选择附件"
            pop.dismiss()

        ok.bind(on_release=choose)
        cancel.bind(on_release=lambda *_a: pop.dismiss())
        pop.open()

    def read_file(self, path):
        data = open(path, "rb").read()
        for enc in ["utf-8-sig", "utf-8", "gb18030", "gbk"]:
            try:
                return parse_numbers(data.decode(enc))
            except Exception:
                pass
        return []

    def _summary_only(self, text):
        """从旧结果文本中只保留统计、形态、闭环等信息，不把组合正文塞进摘要框。"""
        lines = (text or "").splitlines()
        kept = []
        skip_numeric = False
        for line in lines:
            s = line.strip()
            if not s:
                if kept and kept[-1] != "":
                    kept.append("")
                continue
            # section_text/pair_section_text 的标题行保留，后面的纯数字行丢弃
            if s.startswith("【") and ("注" in s or "组" in s):
                kept.append(s)
                skip_numeric = True
                continue
            if re.fullmatch(r"(?:\d{3})(?:\s+\d{3})*", s):
                continue
            if re.fullmatch(r"(?:\d{2})(?:\s+\d{2})*", s):
                continue
            if s == "（无）":
                continue
            kept.append(line)
        while kept and kept[-1] == "":
            kept.pop()
        return "\n".join(kept)

    def _normalize_export_values(self, values):
        if isinstance(values, str):
            # 兼容拆两位功能旧格式；优先抓两/三位纯数字。
            vals = re.findall(r"(?<!\d)(?:\d{2}|\d{3})(?!\d)", values)
            return vals if vals else [values]
        return list(values)

    def _show_message(self, title, message):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        lab = Label(text=message, halign="left", valign="top")
        lab.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0], None)))
        box.add_widget(lab)
        close = Button(text="确定", size_hint_y=None, height=dp(48))
        box.add_widget(close)
        pop = Popup(title=title, content=box, size_hint=(0.92, 0.55))
        close.bind(on_release=lambda *_: pop.dismiss())
        pop.open()

    def _scroll_result_top(self, *_):
        try:
            self.result.cursor = (0, 0)
            self.result.scroll_x = 0
            self.result.scroll_y = 0
        except Exception:
            pass

    def set_exports(self, **named):
        self.current_exports = named
        names = list(named.keys())
        self.result_selector.values = names
        if names:
            self.current_view_name = names[0]
            self.result_selector.text = names[0]
            self.show_result(names[0])
        else:
            self.current_view_name = None
            self.result_selector.text = "选择结果"
            self.page_label.text = ""

    def on_result_selected(self, _spinner, name):
        if name in self.current_exports:
            self.current_view_name = name
            self.show_result(name)

    def show_result(self, name):
        values = self.current_exports.get(name, [])
        if isinstance(values, str):
            body = values
            vals = re.findall(r"(?<!\d)(?:\d{2}|\d{3})(?!\d)", values)
            count = len(vals) if vals else 0
            unit = "组" if vals and all(len(x) == 2 for x in vals) else "注"
        else:
            vals = sorted(set(values))
            body = ("\n".join(" ".join(vals[i:i+10]) for i in range(0, len(vals), 10))) if vals else "（无）"
            count = len(vals)
            unit = "组" if vals and all(len(x) == 2 for x in vals) else "注"
        self.result.text = body
        self.page_label.text = f"{name}｜共 {count} {unit}｜完整显示，可上下滚动"
        Clock.schedule_once(self._scroll_result_top, 0)

    def open_full_result(self, *_):
        name = self.current_view_name
        if not name or name not in self.current_exports:
            self._show_message("提示", "请先选择一个结果。")
            return
        values = self.current_exports[name]
        if isinstance(values, str):
            body = values
        else:
            vals = sorted(set(values))
            body = "\n".join(" ".join(vals[i:i+10]) for i in range(0, len(vals), 10))
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        txt = TextInput(text=body, readonly=True, multiline=True)
        box.add_widget(txt)
        close = Button(text="关闭", size_hint_y=None, height=dp(48))
        box.add_widget(close)
        pop = Popup(title=name, content=box, size_hint=(0.97, 0.95))
        close.bind(on_release=lambda *_: pop.dismiss())
        pop.open()
        def top(*_):
            try:
                txt.cursor=(0,0); txt.scroll_x=0; txt.scroll_y=0
            except Exception:
                pass
        Clock.schedule_once(top, 0.1)

    def export_results(self, *_):
        if not self.current_exports:
            self.result.text += "\n\n没有可导出的结果。"
            return
        export_dir = os.path.join(App.get_running_app().user_data_dir, "exports")
        os.makedirs(export_dir, exist_ok=True)
        written = []
        for name, values in self.current_exports.items():
            safe = re.sub(r"[\\/:*?\"<>|]", "_", name)
            path = os.path.join(export_dir, safe + ".txt")
            text = values if isinstance(values, str) else format_txt(values)
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write(text)
            written.append(path)
        self._show_message("导出完成", "已导出到App目录：\n" + "\n".join(written))

    def _export_items(self):
        """Return [(filename, text), ...] for the current results."""
        items = []
        for name, values in self.current_exports.items():
            safe = re.sub(r'[\\/:*?"<>|]', "_", name)
            filename = safe + ".txt"
            content = values if isinstance(values, str) else format_txt(values)
            items.append((filename, content))
        return items

    def _save_android_download(self, filename, content):
        """Save one TXT into the public Download/数字分析工具 folder on Android."""
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        BuildVersion = autoclass("android.os.Build$VERSION")
        Environment = autoclass("android.os.Environment")

        activity = PythonActivity.mActivity

        if BuildVersion.SDK_INT >= 29:
            MediaStore = autoclass("android.provider.MediaStore")
            ContentValues = autoclass("android.content.ContentValues")
            JavaString = autoclass("java.lang.String")

            resolver = activity.getContentResolver()
            values = ContentValues()
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, filename)
            values.put(MediaStore.MediaColumns.MIME_TYPE, "text/plain")
            values.put(
                MediaStore.MediaColumns.RELATIVE_PATH,
                Environment.DIRECTORY_DOWNLOADS + "/数字分析工具"
            )

            uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            if uri is None:
                raise RuntimeError("Android MediaStore 无法创建下载文件")

            stream = resolver.openOutputStream(uri)
            if stream is None:
                raise RuntimeError("Android 无法打开下载文件输出流")

            # UTF-8 BOM，兼容手机和 Windows 文本工具。
            java_text = JavaString("\ufeff" + content)
            stream.write(java_text.getBytes("UTF-8"))
            stream.flush()
            stream.close()
            return "Download/数字分析工具/" + filename

        # Android 8/9 fallback.
        base = Environment.getExternalStoragePublicDirectory(
            Environment.DIRECTORY_DOWNLOADS
        ).getAbsolutePath()
        folder = os.path.join(base, "数字分析工具")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, filename)
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(content)
        return path

    def export_current_to_download(self, *_):
        name = self.current_view_name
        if not name or name not in self.current_exports:
            self._show_message("提示", "请先选择要保存的结果。")
            return
        if platform != "android":
            self._show_message("提示", "保存到下载仅在Android APK中使用。")
            return
        values = self.current_exports[name]
        safe = re.sub(r'[\\/:*?"<>|]', "_", name)
        filename = safe + ".txt"
        content = values if isinstance(values, str) else format_txt(values)
        try:
            path = self._save_android_download(filename, content)
            self._show_message("保存成功", "已保存：\n" + path)
        except Exception as e:
            self._show_message("保存失败", str(e))

    def export_results_to_download(self, *_):
        if not self.current_exports:
            self._show_message("提示", "没有可保存的结果。")
            return
        if platform != "android":
            self._show_message("提示", "保存到下载仅在Android APK中使用。")
            return
        written, failed = [], []
        for filename, content in self._export_items():
            try:
                written.append(self._save_android_download(filename, content))
            except Exception as e:
                failed.append(f"{filename}：{e}")
        msg = ""
        if written:
            msg += "已保存到 Download/数字分析工具：\n" + "\n".join(written)
        if failed:
            msg += "\n\n保存失败：\n" + "\n".join(failed)
        self._show_message("保存结果", msg or "没有生成文件。")

    def run_analysis(self, *_):
        mode = self.mode.text
        self.current_exports = {}
        self.current_view_name = None
        self.current_page = 0
        self.summary.text = ""
        self.result.text = ""
        self.result_selector.values = ()
        self.result_selector.text = "选择结果"
        self.page_label.text = ""
        try:
            fn = getattr(self, "do_" + str(MODES.index(mode) + 1))
            fn()
            # 各 do_* 仍完全按原逻辑计算；只把原来的长文本拆成“摘要 + 分页结果”。
            raw = self.result.text
            self.summary.text = self._summary_only(raw)
            if self.current_exports:
                # set_exports 已建立完整结果列表；显示当前选择的完整结果。
                if self.current_view_name:
                    self.show_result(self.current_view_name)
            else:
                # 错误提示等没有导出结果的情况，直接显示。
                self.result.text = raw
        except Exception as e:
            self.summary.text = "运行失败"
            self.result.text = f"运行出错：{e}"

    def do_1(self):
        lines = [x.strip() for x in self.input1.text.splitlines() if x.strip()]
        if not lines:
            self.result.text = "请输入口径1条件。"
            return
        out, exports = [], {}
        for line in lines:
            p, err = parse_koujing1(line)
            if err:
                out.append(f"{line}：{err}")
                continue
            r = run_koujing1_normal(p["mother"], p["size_pos"], p["parity_pos"])
            out += [
                f"【{line}】",
                f"母号大小：{r['mother_size']}",
                f"母号奇偶：{r['mother_parity']}",
                "大小正常入选6形态：" + "、".join(r["allowed_size"]),
                "奇偶正常入选6形态：" + "、".join(r["allowed_parity"]),
                f"全量正常出号：{len(r['full'])} 注",
                f"二同+三同：{len(r['same23'])} 注",
                f"三不同：{len(r['different'])} 注",
                f"闭环：{len(r['same23'])} + {len(r['different'])} = {len(r['full'])} √",
                section_text("全量", r["full"]),
                section_text("二同+三同", r["same23"]),
                section_text("三不同", r["different"]),
                ""
            ]
            base = normalize_rule_text(line)
            exports[f"{base}_全量_{len(r['full'])}注"] = r["full"]
            exports[f"{base}_二同三同_{len(r['same23'])}注"] = r["same23"]
            exports[f"{base}_三不同_{len(r['different'])}注"] = r["different"]
        self.result.text = "\n".join(out)
        self.set_exports(**exports)

    def do_2(self):
        size_selected = [x for x in SIZE_SHAPES if x in self.input1.text]
        parity_selected = [x for x in PARITY_SHAPES if x in self.input2.text]
        if not size_selected:
            self.result.text = "请至少输入1个有效的大小形态。"
            return
        if not parity_selected:
            self.result.text = "请至少输入1个有效的奇偶形态。"
            return
        full = [n for n in ALL_NUMBERS if size_shape(n) in size_selected and parity_shape(n) in parity_selected]
        same23 = [n for n in full if repeat_type(n) != "三不同"]
        diff = [n for n in full if repeat_type(n) == "三不同"]
        self.result.text = "\n".join([
            f"大小入选形态（{len(size_selected)}个）：" + "、".join(size_selected),
            f"奇偶入选形态（{len(parity_selected)}个）：" + "、".join(parity_selected),
            f"全量入选：{len(full)} 注",
            f"二同+三同：{len(same23)} 注",
            f"三不同：{len(diff)} 注",
            f"闭环：{len(same23)} + {len(diff)} = {len(full)} √",
            section_text("全量", full),
            section_text("二同+三同", same23),
            section_text("三不同", diff),
        ])
        self.set_exports(**{
            f"形态取号_全量_{len(full)}注": full,
            f"形态取号_二同三同_{len(same23)}注": same23,
            f"形态取号_三不同_{len(diff)}注": diff,
        })

    def do_3(self):
        pa, ea = parse_koujing1(self.input1.text.strip())
        pb, eb = parse_koujing1(self.input2.text.strip())
        if ea or eb:
            self.result.text = f"A：{ea or '正常'}\nB：{eb or '正常'}"
            return
        A = set(run_koujing1(pa["mother"], pa["size_pos"], pa["parity_pos"])["full"])
        B = set(run_koujing1(pb["mother"], pb["size_pos"], pb["parity_pos"])["full"])
        inter = sorted(A & B)
        ao = sorted(A - B)
        bo = sorted(B - A)
        non = sorted((A - B) | (B - A))
        union = sorted(A | B)
        self.result.text = "\n".join([
            f"A全量：{len(A)} 注",
            f"B全量：{len(B)} 注",
            f"交集：{len(inter)} 注",
            f"A独有：{len(ao)} 注",
            f"B独有：{len(bo)} 注",
            f"不交集合并：{len(non)} 注",
            f"合并去重：{len(union)} 注",
            f"闭环：{len(A)} + {len(B)} = 2×{len(inter)} + {len(non)} = {len(A)+len(B)} √",
            section_text("A全量", sorted(A)),
            section_text("B全量", sorted(B)),
            section_text("交集", inter),
            section_text("A独有", ao),
            section_text("B独有", bo),
            section_text("不交集合并", non),
            section_text("合并去重", union),
        ])
        self.set_exports(**{
            f"A全量_{len(A)}注": sorted(A),
            f"B全量_{len(B)}注": sorted(B),
            f"交集_{len(inter)}注": inter,
            f"A独有_{len(ao)}注": ao,
            f"B独有_{len(bo)}注": bo,
            f"不交集合并_{len(non)}注": non,
            f"合并去重_{len(union)}注": union,
        })

    def do_4(self):
        pa, ea = parse_koujing1(self.input1.text.strip())
        pb, eb = parse_koujing1(self.input2.text.strip())
        if ea or eb:
            self.result.text = f"A：{ea or '正常'}\nB：{eb or '正常'}"
            return
        lines = [x.strip() for x in self.input3.text.splitlines() if x.strip()]
        if len(lines) < 5:
            self.result.text = "输入3需要：第1行数字轨，后4行形态轨。"
            return
        digits = parse_digit_track(lines[0])
        shapes = lines[1:5]
        if not digits or any(classify_shape_token(x) is None for x in shapes):
            self.result.text = "数字轨或4个形态轨无法识别。"
            return
        A = set(run_koujing1(pa["mother"], pa["size_pos"], pa["parity_pos"])["different"])
        B = set(run_koujing1(pb["mother"], pb["size_pos"], pb["parity_pos"])["different"])
        inter = sorted(A & B)
        ao = sorted(A - B)
        bo = sorted(B - A)
        non = sorted((A - B) | (B - A))
        db, bc = run_digit_track(non, digits)
        valid_shapes, sb, cd = run_shape_track(non, shapes)
        final_in = sorted(set(bc) & set(cd))
        final_out = sorted(set(non) - set(final_in))
        out = [
            f"A三不同：{len(A)} 注",
            f"B三不同：{len(B)} 注",
            f"交集：{len(inter)} 注",
            f"A独有：{len(ao)} 注",
            f"B独有：{len(bo)} 注",
            f"不交集合并：{len(non)} 注",
            f"前置闭环：{len(A)} + {len(B)} = 2×{len(inter)} + {len(non)} = {len(A)+len(B)} √",
            section_text("A三不同", sorted(A)),
            section_text("B三不同", sorted(B)),
            section_text("交集", inter),
            section_text("A独有", ao),
            section_text("B独有", bo),
            section_text("不交集合并", non),
            "数字轨目标：" + "、".join(digits),
        ]
        for count in sorted(db):
            out.append(section_text(f"数字轨出现{count}次", db[count]))
        out += [
            section_text("数字BC（2次+3次）", bc),
            "形态轨：" + "、".join(x for x, _ in valid_shapes),
        ]
        for count in sorted(sb):
            out.append(section_text(f"形态轨出现{count}次", sb[count]))
        out += [
            section_text("形态CD（3次+4次）", cd),
            section_text("最终入选 BC∩CD", final_in),
            section_text("最终不入选", final_out),
            f"最终闭环：{len(final_in)} + {len(final_out)} = {len(non)} √",
        ]
        self.result.text = "\n".join(out)
        exports = {
            f"A三不同_{len(A)}注": sorted(A),
            f"B三不同_{len(B)}注": sorted(B),
            f"交集_{len(inter)}注": inter,
            f"A独有_{len(ao)}注": ao,
            f"B独有_{len(bo)}注": bo,
            f"不交集合并_{len(non)}注": non,
            f"数字BC_{len(bc)}注": bc,
            f"形态CD_{len(cd)}注": cd,
            f"最终入选_{len(final_in)}注": final_in,
            f"最终不入选_{len(final_out)}注": final_out,
        }
        for count, vals in db.items():
            exports[f"数字轨_出现{count}次_{len(vals)}注"] = vals
        for count, vals in sb.items():
            exports[f"形态轨_出现{count}次_{len(vals)}注"] = vals
        self.set_exports(**exports)

    def need_files(self, count=None, minimum=None):
        n = len(self.loaded_files)
        if count is not None and n != count:
            self.result.text = f"需要选择 {count} 个TXT附件，目前 {n} 个。"
            return False
        if minimum is not None and n < minimum:
            self.result.text = f"至少需要选择 {minimum} 个TXT附件，目前 {n} 个。"
            return False
        return True

    def do_5(self):
        if not self.need_files(count=2):
            return
        A = set(self.read_file(self.loaded_files[0]))
        B = set(self.read_file(self.loaded_files[1]))
        inter = sorted(A & B)
        ao = sorted(A - B)
        bo = sorted(B - A)
        non = sorted((A - B) | (B - A))
        union = sorted(A | B)
        self.result.text = "\n".join([
            f"A：{len(A)} 注", f"B：{len(B)} 注", f"交集：{len(inter)} 注",
            f"A独有：{len(ao)} 注", f"B独有：{len(bo)} 注",
            f"不交集合并：{len(non)} 注", f"合并去重：{len(union)} 注",
            f"闭环：{len(A)} + {len(B)} = 2×{len(inter)} + {len(non)} = {len(A)+len(B)} √",
            section_text("交集", inter), section_text("A独有", ao), section_text("B独有", bo),
            section_text("不交集合并", non), section_text("合并去重", union),
        ])
        self.set_exports(**{
            f"交集_{len(inter)}注": inter,
            f"A独有_{len(ao)}注": ao,
            f"B独有_{len(bo)}注": bo,
            f"不交集合并_{len(non)}注": non,
            f"合并去重_{len(union)}注": union,
        })

    def do_6(self):
        if not self.need_files(minimum=2):
            return
        A = set(self.read_file(self.loaded_files[0]))
        out = [f"A：{len(A)} 注"]
        exports = {}
        for i, path in enumerate(self.loaded_files[1:], start=1):
            label = chr(65 + i)
            B = set(self.read_file(path))
            inter = sorted(A & B)
            ao = sorted(A - B)
            bo = sorted(B - A)
            non = sorted((A - B) | (B - A))
            out += [
                f"\n【A 与 {label}】{os.path.basename(path)}",
                f"{label}：{len(B)} 注",
                f"A∩{label}：{len(inter)} 注",
                f"A独有：{len(ao)} 注",
                f"{label}独有：{len(bo)} 注",
                f"不交集合并：{len(non)} 注",
                f"闭环：{len(A)} + {len(B)} = 2×{len(inter)} + {len(non)} = {len(A)+len(B)} √",
                section_text(f"A∩{label}", inter),
                section_text(f"A独有（相对{label}）", ao),
                section_text(f"{label}独有", bo),
                section_text(f"A与{label}不交集合并", non),
            ]
            exports[f"A与{label}交集_{len(inter)}注"] = inter
            exports[f"A对{label}独有_{len(ao)}注"] = ao
            exports[f"{label}独有_{len(bo)}注"] = bo
            exports[f"A与{label}不交集合并_{len(non)}注"] = non
        self.result.text = "\n".join(out)
        self.set_exports(**exports)

    def do_7(self):
        if not self.need_files(minimum=2):
            return
        sets, details, total = [], [], 0
        for p in self.loaded_files:
            vals = set(self.read_file(p))
            sets.append(vals)
            total += len(vals)
            details.append(f"{os.path.basename(p)}：{len(vals)} 注")
        merged = sorted(set().union(*sets))
        dup = total - len(merged)
        self.result.text = "\n".join(details + [
            f"累计：{total} 注",
            f"合并去重：{len(merged)} 注",
            f"重复计数：{dup}",
            f"闭环：{total} - {dup} = {len(merged)} √",
            section_text("合并去重", merged),
        ])
        self.set_exports(**{f"合并去重_{len(merged)}注": merged})

    def do_8(self):
        if not self.need_files(count=1):
            return
        size_remove = [x for x in SIZE_SHAPES if x in self.input1.text]
        parity_remove = [x for x in PARITY_SHAPES if x in self.input2.text]
        original = self.read_file(self.loaded_files[0])
        remain, removed = [], []
        for n in original:
            bad = size_shape(n) in size_remove or parity_shape(n) in parity_remove
            (removed if bad else remain).append(n)
        self.result.text = "\n".join([
            f"原始：{len(original)} 注",
            f"剩余：{len(remain)} 注",
            f"去掉：{len(removed)} 注",
            f"闭环：{len(remain)} + {len(removed)} = {len(original)} √",
            section_text("剩余组合", remain),
            section_text("被去掉组合", removed),
        ])
        self.set_exports(**{
            f"剩余_{len(remain)}注": remain,
            f"被去掉_{len(removed)}注": removed,
        })

    def do_9(self):
        if not self.need_files(count=1):
            return
        original = self.read_file(self.loaded_files[0])
        two, three, diff = [], [], []
        for n in original:
            t = repeat_type(n)
            (two if t == "二同" else three if t == "三同" else diff).append(n)
        same = sorted(two + three)
        self.result.text = "\n".join([
            f"原始：{len(original)} 注",
            f"二同：{len(two)} 注",
            f"三同：{len(three)} 注",
            f"二同+三同：{len(same)} 注",
            f"三不同：{len(diff)} 注",
            f"闭环：{len(same)} + {len(diff)} = {len(original)} √",
            section_text("二同+三同", same),
            section_text("三不同", diff),
            section_text("二同", two),
            section_text("三同", three),
        ])
        self.set_exports(**{
            f"二同三同_{len(same)}注": same,
            f"三不同_{len(diff)}注": diff,
            f"二同_{len(two)}注": two,
            f"三同_{len(three)}注": three,
        })

    def parse_pair_mode(self):
        t = self.input2.text.strip()
        if "恰好" in t:
            return "恰好两对命中"
        if "三" in t and "全" in t:
            return "三对全命中"
        return "两对命中（至少2对）"

    def pair_common(self, base, prefix=""):
        pairs = parse_pair_conditions(self.input1.text)
        if not pairs:
            self.result.text = "请输入有效两位组合。"
            return
        pmode = self.parse_pair_mode()
        selected, rejected = run_pair_filter(base, pairs, pmode)
        same = [n for n in selected if repeat_type(n) != "三不同"]
        diff = [n for n in selected if repeat_type(n) == "三不同"]
        self.result.text = "\n".join([
            f"两位条件：{len(pairs)}组",
            f"模式：{pmode}",
            f"原始：{len(base)} 注",
            f"符合：{len(selected)} 注",
            f"不符合：{len(rejected)} 注",
            f"符合中的二同+三同：{len(same)} 注",
            f"符合中的三不同：{len(diff)} 注",
            f"总闭环：{len(selected)} + {len(rejected)} = {len(base)} √",
            f"分类闭环：{len(same)} + {len(diff)} = {len(selected)} √",
            section_text("符合条件全量", selected),
            section_text("不符合条件", rejected),
            section_text("二同+三同", same),
            section_text("三不同", diff),
        ])
        self.set_exports(**{
            f"{prefix}两位命中_符合_{len(selected)}注": selected,
            f"{prefix}两位命中_不符合_{len(rejected)}注": rejected,
            f"{prefix}两位命中_二同三同_{len(same)}注": same,
            f"{prefix}两位命中_三不同_{len(diff)}注": diff,
        })

    def do_10(self):
        if not self.need_files(count=1):
            return
        self.pair_common(self.read_file(self.loaded_files[0]))

    def do_11(self):
        self.pair_common(ALL_NUMBERS, prefix="000-999_")

    def do_12(self):
        if not self.need_files(count=1):
            return
        digits = []
        for c in self.input1.text:
            if c.isdigit() and c not in digits:
                digits.append(c)
        if not digits:
            self.result.text = "请输入数字。"
            return
        lines = [x.strip() for x in self.input2.text.splitlines() if x.strip()]
        match_all = bool(lines and "全部" in lines[0])
        remove_action = bool(len(lines) > 1 and "去" in lines[1])
        original = self.read_file(self.loaded_files[0])
        matched, unmatched = [], []
        for n in original:
            ok = all(d in n for d in digits) if match_all else any(d in n for d in digits)
            (matched if ok else unmatched).append(n)
        if remove_action:
            result, other, rn, on = unmatched, matched, "去掉后剩余", "被去掉"
        else:
            result, other, rn, on = matched, unmatched, "符合条件", "不符合条件"
        self.result.text = "\n".join([
            "数字：" + "、".join(digits),
            "判断方式：" + ("必须同时含全部" if match_all else "含任意一个"),
            "操作：" + ("去掉符合条件的组合" if remove_action else "筛出符合条件的组合"),
            f"原始：{len(original)} 注",
            f"{rn}：{len(result)} 注",
            f"{on}：{len(other)} 注",
            f"闭环：{len(result)} + {len(other)} = {len(original)} √",
            section_text(rn, result),
            section_text(on, other),
        ])
        self.set_exports(**{
            f"{rn}_{len(result)}注": result,
            f"{on}_{len(other)}注": other,
        })

    def do_13(self):
        tokens = parse_split_inputs(self.input1.text)
        if not tokens:
            self.result.text = "请输入3-7位数字。"
            return
        out, merged, exports = [], set(), {}
        for t in tokens:
            pairs = split_to_pairs(t)
            merged.update(pairs)
            out.append(pair_section_text(t, pairs))
            exports[f"{t}_拆两位_{len(pairs)}组"] = pairs
        merged = sorted(merged)
        out.append(pair_section_text("全部合并去重", merged))
        exports[f"三至七位拆两位_合并去重_{len(merged)}组"] = merged
        self.result.text = "\n\n".join(out)
        self.set_exports(**exports)

    def do_14(self):
        if not self.need_files(count=1):
            return
        original = self.read_file(self.loaded_files[0])
        half = [n for n in original if sequence_type(n) == "半顺"]
        full = [n for n in original if sequence_type(n) == "全顺"]
        non = [n for n in original if sequence_type(n) == "非半顺"]
        hm = sorted(half + full)
        self.result.text = "\n".join([
            f"原始：{len(original)} 注",
            f"半顺：{len(half)} 注",
            f"全顺：{len(full)} 注",
            f"半顺以上：{len(hm)} 注",
            f"非半顺以上：{len(non)} 注",
            f"分类闭环1：{len(half)} + {len(full)} = {len(hm)} √",
            f"分类闭环2：{len(hm)} + {len(non)} = {len(original)} √",
            section_text("半顺以上", hm),
            section_text("半顺", half),
            section_text("全顺", full),
            section_text("非半顺以上", non),
        ])
        self.set_exports(**{
            f"半顺以上_{len(hm)}注": hm,
            f"半顺_{len(half)}注": half,
            f"全顺_{len(full)}注": full,
            f"非半顺以上_{len(non)}注": non,
        })


class NumberAnalysisApp(App):
    def build(self):
        self.title = "数字分析工具"
        content = NumberAnalysisRoot(size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        scroller = ScrollView(do_scroll_x=False, do_scroll_y=True)
        scroller.add_widget(content)
        return scroller


if __name__ == "__main__":
    NumberAnalysisApp().run()
