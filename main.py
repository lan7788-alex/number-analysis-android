import os
import re
from itertools import combinations

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.utils import platform

# Android 输入改用系统原生 EditText/AlertDialog，彻底绕开 Kivy TextInput 的触摸/焦点链路。
if platform == "android":
    from android.runnable import run_on_ui_thread
    from jnius import PythonJavaClass, java_method

    class _DialogClickListener(PythonJavaClass):
        __javainterfaces__ = ["android/content/DialogInterface$OnClickListener"]
        __javacontext__ = "app"

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method("(Landroid/content/DialogInterface;I)V")
        def onClick(self, dialog, which):
            if self.callback:
                self.callback()
else:
    def run_on_ui_thread(func):
        return func

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


# Android上保持Kivy默认软键盘模式。
# 不使用 below_target，避免视口平移后视觉位置与触摸坐标短暂不同步。
if platform == "android":
    try:
        Window.softinput_mode = ""
    except Exception:
        pass


class MobileTextInput(TextInput):
    """手机输入框：只扩大可点击区域，不改写Kivy原生触摸与焦点事件。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("font_size", "18sp")
        kwargs.setdefault("padding", [dp(12), dp(12), dp(12), dp(12)])
        kwargs.setdefault("cursor_width", dp(2))
        kwargs.setdefault("write_tab", False)
        kwargs.setdefault("use_bubble", False)
        kwargs.setdefault("use_handles", False)
        super().__init__(**kwargs)


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
        super().__init__(orientation="vertical", spacing=dp(6), padding=dp(6), **kwargs)

        # -------------------------
        # 数据状态
        # -------------------------
        self.loaded_files = []
        self.file_A = None
        self.file_B = None
        self.file_single = None
        self.file_others = []
        self._append_uri_keys = set()
        self._picker_target = "single"
        self.current_exports = {}
        self.current_view_name = None
        self._native_dialog_refs = None

        # 这三个 TextInput 只作为“数据容器”，不直接参与触摸输入。
        # 所有业务输入都改为“纯按钮选择/数字键盘/剪贴板导入”，
        # 避开 Android/Kivy/输入法的焦点链路。
        self.input1 = MobileTextInput(multiline=True)
        self.input2 = MobileTextInput(multiline=True)
        self.input3 = MobileTextInput(multiline=True)
        self._input_widgets = [self.input1, self.input2, self.input3]
        self._input_hints = ["", "", ""]
        self._input_titles = ["输入1", "输入2", "输入3"]

        # -------------------------
        # 标题 + 功能选择
        # -------------------------
        self.add_widget(Label(
            text="数字分析工具（离线版）",
            size_hint_y=None,
            height=dp(34),
            font_size="19sp"
        ))

        self.mode = Spinner(
            text=MODES[0],
            values=MODES,
            size_hint_y=None,
            height=dp(58),
            font_size="16sp"
        )
        self.mode.bind(text=self.on_mode_change)
        self.add_widget(self.mode)

        self.instructions = Label(
            text="",
            size_hint_y=None,
            height=dp(46),
            halign="left",
            valign="middle",
            font_size="13sp"
        )
        self.instructions.bind(
            size=lambda inst, val: setattr(inst, "text_size", (val[0], None))
        )
        self.add_widget(self.instructions)

        # -------------------------
        # 手机专用输入区：主界面只放“大按钮”
        # -------------------------
        self.input_buttons = []
        for i in range(3):
            btn = Button(
                text=f"点击设置{i+1}",
                size_hint_y=None,
                height=dp(60),
                font_size="15sp",
                halign="left",
                valign="middle"
            )
            btn.bind(
                size=lambda inst, val: setattr(inst, "text_size", (max(dp(10), val[0]-dp(18)), None))
            )
            btn.bind(on_release=lambda _btn, idx=i: self.open_input_editor(idx))
            self.input_buttons.append(btn)
            self.add_widget(btn)

        # -------------------------
        # 附件区
        # -------------------------
        self.file_row = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(116),
            spacing=dp(6)
        )

        self.file_button_row = BoxLayout(
            size_hint_y=None,
            height=dp(56),
            spacing=dp(6)
        )
        self.file_row.add_widget(self.file_button_row)

        self.files_label = Label(
            text="未选择附件",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(54),
            font_size="14sp"
        )
        self.files_label.bind(
            size=lambda inst, val: setattr(inst, "text_size", (val[0], val[1]))
        )
        self.file_row.add_widget(self.files_label)
        self.add_widget(self.file_row)

        # -------------------------
        # 分析 / 清空
        # -------------------------
        action_row = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(6))
        brun = Button(text="开始分析", font_size="16sp")
        brun.bind(on_release=self.run_analysis)
        bclear = Button(text="清空", font_size="16sp")
        bclear.bind(on_release=self.clear_all)
        action_row.add_widget(brun)
        action_row.add_widget(bclear)
        self.add_widget(action_row)

        # -------------------------
        # 摘要 + 结果
        # -------------------------
        self.summary = TextInput(
            readonly=True,
            multiline=True,
            is_focusable=False,
            size_hint_y=None,
            height=dp(88),
            hint_text="分析摘要",
            font_size="14sp"
        )
        self.add_widget(self.summary)

        self.result_selector = Spinner(
            text="选择查看结果",
            values=(),
            size_hint_y=None,
            height=dp(56),
            font_size="15sp"
        )
        self.result_selector.bind(text=self.on_result_selected)
        self.add_widget(self.result_selector)

        self.result = TextInput(
            readonly=True,
            multiline=True,
            is_focusable=False,
            size_hint_y=1,
            hint_text="分析后这里直接显示完整组合，10注一行",
            font_size="15sp"
        )
        self.add_widget(self.result)

        # -------------------------
        # 复制 / 保存
        # -------------------------
        copy_row = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(6))
        bcopy = Button(text="复制当前结果", font_size="15sp")
        bcopy.bind(on_release=self.copy_current_result)
        bcopyall = Button(text="复制全部结果", font_size="15sp")
        bcopyall.bind(on_release=self.copy_all_results)
        copy_row.add_widget(bcopy)
        copy_row.add_widget(bcopyall)
        self.add_widget(copy_row)

        save_row = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(6))
        bcurrent = Button(text="保存当前到下载", font_size="15sp")
        bcurrent.bind(on_release=self.export_current_to_download)
        ball = Button(text="保存全部到下载", font_size="15sp")
        ball.bind(on_release=self.export_results_to_download)
        save_row.add_widget(bcurrent)
        save_row.add_widget(ball)
        self.add_widget(save_row)

        self.on_mode_change(self.mode, self.mode.text)



    def _unfocus_inputs(self, *_):
        """主界面不再直接放可编辑 TextInput；这里只负责关闭残余键盘焦点。"""
        for widget in self._input_widgets:
            try:
                widget.focus = False
            except Exception:
                pass


    def _mode_input_titles(self, mode):
        titles = {
            "口径1取号": ["口径1条件"],
            "形态取号": ["大小 + 奇偶形态"],
            "口径1双条件全量交集": ["A条件", "B条件"],
            "口径1交集后数字形态轨": ["A条件", "B条件", "数字轨 + 4个形态轨"],
            "形态筛选": ["要去掉的大小形态", "要去掉的奇偶形态"],
            "两位组合命中筛选（按附件）": ["两位组合", "命中模式"],
            "两位组合命中筛选（000-999）": ["两位组合", "命中模式"],
            "数字包含 / 去除筛选": ["目标数字", "筛选模式"],
            "三至七位拆两位组合": ["3-7位数字"],
        }
        vals = titles.get(mode, [])
        vals = vals + [f"输入{i+1}" for i in range(len(vals), 3)]
        return vals[:3]

    def _short_preview(self, text, max_len=38):
        clean = " ".join((text or "").split())
        if not clean:
            return ""
        if len(clean) <= max_len:
            return clean
        return clean[:max_len] + "…"

    def _update_input_buttons(self):
        for i, btn in enumerate(self.input_buttons):
            if btn.height <= 0:
                continue
            title = self._input_titles[i]
            value = self._short_preview(self._input_widgets[i].text)
            if value:
                btn.text = f"{title}：{value}\n（点击修改）"
            else:
                hint = self._short_preview(self._input_hints[i], 44)
                btn.text = f"点击设置：{title}\n{hint}"


    def open_input_editor(self, index):
        """
        纯按钮输入总入口。

        不再打开 Android EditText / Kivy TextInput 键盘输入框。
        需要文字量较大的项目（两位组合、3-7位组合）提供“从剪贴板导入”。
        """
        if not 0 <= index < 3:
            return

        mode = self.mode.text

        if mode == "口径1取号" and index == 0:
            self._open_rule_button_editor(index, allow_multiple=True)
            return

        if mode == "形态取号" and index == 0:
            self._open_shape_button_editor(index, "both")
            return

        if mode == "口径1双条件全量交集" and index in (0, 1):
            self._open_rule_button_editor(index, allow_multiple=False)
            return

        if mode == "口径1交集后数字形态轨":
            if index in (0, 1):
                self._open_rule_button_editor(index, allow_multiple=False)
            elif index == 2:
                self._open_track_button_editor(index)
            return

        if mode == "形态筛选":
            if index == 0:
                self._open_shape_button_editor(index, "size")
            elif index == 1:
                self._open_shape_button_editor(index, "parity")
            return

        if mode in {"两位组合命中筛选（按附件）", "两位组合命中筛选（000-999）"}:
            if index == 0:
                self._open_pair_button_editor(index)
            elif index == 1:
                self._open_pair_mode_editor(index)
            return

        if mode == "数字包含 / 去除筛选":
            if index == 0:
                self._open_digit_select_editor(index)
            elif index == 1:
                self._open_digit_filter_mode_editor(index)
            return

        if mode == "三至七位拆两位组合" and index == 0:
            self._open_split_button_editor(index)
            return

        # 理论上不会走到这里；保留兼容提示，不再调用任何键盘输入框。
        self._show_message("输入方式", "这个位置当前没有可用的按钮输入面板。")

    def _popup_shell(self, title):
        """
        创建纯按钮弹窗。

        重要：这里不再使用 ScrollView。
        Kivy ScrollView 会先截获触摸来判断用户是在滚动还是点击，
        在部分三星手机上会让里面的按钮出现“点很多次才响应”的感觉。
        现在按钮直接放在普通 BoxLayout 中，触摸路径和主界面的
        “选择A附件”按钮一致。
        """
        body = BoxLayout(
            orientation="vertical",
            spacing=dp(5),
            padding=[dp(5), dp(5), dp(5), dp(6)],
            size_hint=(1, 1)
        )
        popup = Popup(
            title=title,
            content=body,
            size_hint=(0.98, 0.95),
            auto_dismiss=False
        )
        return popup, body

    def _add_label(self, body, text, height=48, font_size="14sp"):
        lab = Label(
            text=text,
            size_hint_y=None,
            height=dp(height),
            halign="left",
            valign="middle",
            font_size=font_size
        )
        lab.bind(size=lambda inst, val: setattr(inst, "text_size", (max(dp(10), val[0]-dp(8)), None)))
        body.add_widget(lab)
        return lab

    def _add_button_grid(self, body, specs, cols=3, height=52):
        """specs: [(text, callback), ...]"""
        rows = max(1, (len(specs) + cols - 1) // cols)
        grid = GridLayout(
            cols=cols,
            spacing=dp(5),
            size_hint_y=None,
            height=dp(height) * rows + dp(5) * max(0, rows-1)
        )
        for txt, cb in specs:
            b = Button(text=txt, font_size="15sp")
            b.bind(on_release=cb)
            grid.add_widget(b)
        body.add_widget(grid)
        return grid

    def _open_rule_button_editor(self, index, allow_multiple=False):
        """口径1条件：数字键 + 大小取位 + 奇偶取位，全程无输入框。"""
        target = self._input_widgets[index]
        title = self._input_titles[index]
        popup, body = self._popup_shell(title)

        existing_lines = [x.strip() for x in target.text.splitlines() if x.strip()]
        if not allow_multiple and len(existing_lines) > 1:
            existing_lines = existing_lines[:1]

        state = {
            "mother": "",
            "size_pos": None,
            "parity_pos": None,
            "lines": list(existing_lines),
        }

        # 单条件编辑时，尝试把已有值载入按钮状态。
        if not allow_multiple and existing_lines:
            parsed, err = parse_koujing1(existing_lines[0])
            if not err:
                state["mother"] = parsed["mother"]
                state["size_pos"] = parsed["size_pos"]
                state["parity_pos"] = parsed["parity_pos"]

        preview = self._add_label(body, "", height=72, font_size="16sp")
        self._add_label(body, "① 点数字组成3位母号", height=40)

        digit_specs = []
        for d in "1234567890":
            def make_digit_cb(x):
                def cb(*_):
                    if len(state["mother"]) < 3:
                        state["mother"] += x
                        refresh()
                return cb
            digit_specs.append((d, make_digit_cb(d)))
        self._add_button_grid(body, digit_specs, cols=5, height=50)

        row_specs = [
            ("退一位", lambda *_: (state.__setitem__("mother", state["mother"][:-1]), refresh())),
            ("清空母号", lambda *_: (state.__setitem__("mother", ""), refresh())),
        ]
        self._add_button_grid(body, row_specs, cols=2, height=50)

        self._add_label(body, "② 选择大小取位", height=38)
        size_buttons = {}
        size_grid = GridLayout(cols=3, spacing=dp(5), size_hint_y=None, height=dp(52))
        for pos in ("百十", "百个", "十个"):
            b = Button(text=pos, font_size="15sp")
            size_buttons[pos] = b
            def choose_size(_btn, p=pos):
                state["size_pos"] = p
                refresh()
            b.bind(on_release=choose_size)
            size_grid.add_widget(b)
        body.add_widget(size_grid)

        self._add_label(body, "③ 选择奇偶取位", height=38)
        parity_buttons = {}
        parity_grid = GridLayout(cols=3, spacing=dp(5), size_hint_y=None, height=dp(52))
        for pos in ("百十", "百个", "十个"):
            b = Button(text=pos, font_size="15sp")
            parity_buttons[pos] = b
            def choose_parity(_btn, p=pos):
                state["parity_pos"] = p
                refresh()
            b.bind(on_release=choose_parity)
            parity_grid.add_widget(b)
        body.add_widget(parity_grid)

        def build_current():
            if len(state["mother"]) != 3 or not state["size_pos"] or not state["parity_pos"]:
                return None
            if state["size_pos"] == state["parity_pos"]:
                return state["mother"] + state["size_pos"]
            return (
                state["mother"]
                + "大小" + state["size_pos"]
                + "奇偶" + state["parity_pos"]
            )

        def refresh():
            cur = build_current()
            current_text = cur or (
                f"母号：{state['mother'] or '未完成'}；"
                f"大小：{state['size_pos'] or '未选'}；"
                f"奇偶：{state['parity_pos'] or '未选'}"
            )
            if allow_multiple:
                saved = "\n".join(state["lines"]) if state["lines"] else "暂无"
                preview.text = f"当前：{current_text}\n已保存：{saved}"
            else:
                preview.text = f"当前条件：{current_text}"
            for p, b in size_buttons.items():
                b.text = ("✓ " if state["size_pos"] == p else "") + p
            for p, b in parity_buttons.items():
                b.text = ("✓ " if state["parity_pos"] == p else "") + p

        if allow_multiple:
            def add_line(*_):
                cur = build_current()
                if not cur:
                    self._show_message("条件未完成", "请先输入3位母号，并选择大小取位和奇偶取位。")
                    return
                state["lines"].append(cur)
                state["mother"] = ""
                state["size_pos"] = None
                state["parity_pos"] = None
                refresh()

            def delete_last(*_):
                if state["lines"]:
                    state["lines"].pop()
                refresh()

            self._add_button_grid(body, [
                ("添加本条", add_line),
                ("删除末条", delete_last),
                ("清空全部", lambda *_: (state["lines"].clear(), state.__setitem__("mother", ""), state.__setitem__("size_pos", None), state.__setitem__("parity_pos", None), refresh())),
            ], cols=3, height=52)

            def commit(*_):
                cur = build_current()
                if cur:
                    state["lines"].append(cur)
                if not state["lines"]:
                    self._show_message("没有条件", "请至少添加1条口径1条件。")
                    return
                target.text = "\n".join(state["lines"])
                self._update_input_buttons()
                popup.dismiss()
        else:
            def commit(*_):
                cur = build_current()
                if not cur:
                    self._show_message("条件未完成", "请先输入3位母号，并选择大小取位和奇偶取位。")
                    return
                target.text = cur
                self._update_input_buttons()
                popup.dismiss()

        self._add_button_grid(body, [
            ("确定", commit),
            ("取消", lambda *_: popup.dismiss()),
        ], cols=2, height=56)

        refresh()
        popup.open()

    def _open_shape_button_editor(self, index, kind="both"):
        """大小/奇偶形态直接点选，完全不用键盘。"""
        target = self._input_widgets[index]
        popup, body = self._popup_shell(self._input_titles[index])

        allowed = []
        if kind in ("both", "size"):
            allowed += SIZE_SHAPES
        if kind in ("both", "parity"):
            allowed += PARITY_SHAPES

        selected = {x for x in allowed if x in (target.text or "")}
        status = self._add_label(body, "", height=52, font_size="14sp")
        buttons = {}

        def refresh():
            for shape, b in buttons.items():
                b.text = ("✓ " if shape in selected else "") + shape
            s = [x for x in SIZE_SHAPES if x in selected]
            p = [x for x in PARITY_SHAPES if x in selected]
            parts = []
            if kind in ("both", "size"):
                parts.append(f"大小已选 {len(s)} 个")
            if kind in ("both", "parity"):
                parts.append(f"奇偶已选 {len(p)} 个")
            status.text = "；".join(parts) + "\n再次点击可取消。"

        def add_shape_section(label_text, shapes):
            self._add_label(body, label_text, height=38)
            grid = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(43)*4 + dp(12))
            for shape in shapes:
                b = Button(text=shape, font_size="15sp")
                buttons[shape] = b
                def toggle(_btn, s=shape):
                    if s in selected:
                        selected.remove(s)
                    else:
                        selected.add(s)
                    refresh()
                b.bind(on_release=toggle)
                grid.add_widget(b)
            body.add_widget(grid)

        if kind in ("both", "size"):
            add_shape_section("大小形态", SIZE_SHAPES)
        if kind in ("both", "parity"):
            add_shape_section("奇偶形态", PARITY_SHAPES)

        def select_all(*_):
            selected.update(allowed)
            refresh()

        def clear_all(*_):
            selected.clear()
            refresh()

        def commit(*_):
            ordered = [x for x in SIZE_SHAPES + PARITY_SHAPES if x in selected]
            target.text = "\n".join(ordered)
            self._update_input_buttons()
            popup.dismiss()

        self._add_button_grid(body, [
            ("全选", select_all),
            ("清空", clear_all),
            ("确定", commit),
            ("取消", lambda *_: popup.dismiss()),
        ], cols=2, height=52)
        refresh()
        popup.open()

    def _open_track_button_editor(self, index):
        """数字形态轨：点选数字 + 4个形态。"""
        target = self._input_widgets[index]
        popup, body = self._popup_shell(self._input_titles[index])

        lines = [x.strip() for x in target.text.splitlines() if x.strip()]
        selected_digits = set(parse_digit_track(lines[0]) if lines else [])
        selected_shapes = [x for x in lines[1:5] if classify_shape_token(x)] if len(lines) > 1 else []

        status = self._add_label(body, "", height=54, font_size="14sp")
        digit_buttons = {}
        shape_buttons = {}

        self._add_label(body, "① 点选数字轨目标（可多选）", height=38)
        dgrid = GridLayout(cols=5, spacing=dp(5), size_hint_y=None, height=dp(105))
        for d in "0123456789":
            b = Button(text=d, font_size="16sp")
            digit_buttons[d] = b
            def toggle_digit(_btn, x=d):
                if x in selected_digits:
                    selected_digits.remove(x)
                else:
                    selected_digits.add(x)
                refresh()
            b.bind(on_release=toggle_digit)
            dgrid.add_widget(b)
        body.add_widget(dgrid)

        self._add_label(body, "② 点选4个形态轨（大小/奇偶可混合）", height=42)
        sgrid = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(42)*8 + dp(24))
        for shape in SIZE_SHAPES + PARITY_SHAPES:
            b = Button(text=shape, font_size="15sp")
            shape_buttons[shape] = b
            def toggle_shape(_btn, s=shape):
                if s in selected_shapes:
                    selected_shapes.remove(s)
                else:
                    if len(selected_shapes) >= 4:
                        self._show_message("最多4个形态", "形态轨固定选择4个。请先取消一个再选新的。")
                        return
                    selected_shapes.append(s)
                refresh()
            b.bind(on_release=toggle_shape)
            sgrid.add_widget(b)
        body.add_widget(sgrid)

        def refresh():
            for d, b in digit_buttons.items():
                b.text = ("✓ " if d in selected_digits else "") + d
            for s, b in shape_buttons.items():
                b.text = ("✓ " if s in selected_shapes else "") + s
            status.text = (
                "数字：" + (" ".join(sorted(selected_digits)) if selected_digits else "未选")
                + f"\n形态：{len(selected_shapes)}/4 "
                + ("、".join(selected_shapes) if selected_shapes else "未选")
            )

        def commit(*_):
            if not selected_digits:
                self._show_message("数字未选择", "请至少选择1个数字轨目标。")
                return
            if len(selected_shapes) != 4:
                self._show_message("形态数量不对", "形态轨必须正好选择4个形态。")
                return
            target.text = "数字" + "".join(sorted(selected_digits)) + "\n" + "\n".join(selected_shapes)
            self._update_input_buttons()
            popup.dismiss()

        self._add_button_grid(body, [
            ("清空全部", lambda *_: (selected_digits.clear(), selected_shapes.clear(), refresh())),
            ("确定", commit),
            ("取消", lambda *_: popup.dismiss()),
        ], cols=3, height=52)
        refresh()
        popup.open()

    def _open_pair_button_editor(self, index):
        """两位组合：数字按钮手动添加，或从剪贴板一键导入。"""
        target = self._input_widgets[index]
        popup, body = self._popup_shell(self._input_titles[index])

        pairs = sorted(parse_pair_conditions(target.text))
        buffer = {"text": ""}
        status = self._add_label(body, "", height=92, font_size="14sp")

        def refresh():
            preview = " ".join(pairs[:35])
            if len(pairs) > 35:
                preview += " ……"
            status.text = (
                f"当前两位：{buffer['text'] or '未输入'}\n"
                f"已选 {len(pairs)} 组：{preview or '暂无'}"
            )

        def add_digit(d):
            if len(buffer["text"]) >= 2:
                buffer["text"] = ""
            buffer["text"] += d
            if len(buffer["text"]) == 2:
                p = canonical_pair(buffer["text"])
                if p and p not in pairs:
                    pairs.append(p)
                    pairs.sort()
                buffer["text"] = ""
            refresh()

        specs = []
        for d in "0123456789":
            specs.append((d, lambda _b, x=d: add_digit(x)))
        self._add_button_grid(body, specs, cols=5, height=50)

        def import_clip(*_):
            clip = Clipboard.paste() or ""
            found = sorted(parse_pair_conditions(clip))
            if not found:
                self._show_message("剪贴板没有两位组合", "请先复制类似 01 03 15 68 的两位组合。")
                return
            pairs[:] = found
            buffer["text"] = ""
            refresh()

        def remove_last(*_):
            if pairs:
                pairs.pop()
            refresh()

        def commit(*_):
            if not pairs:
                self._show_message("没有两位组合", "请手动点数字添加，或从剪贴板导入。")
                return
            target.text = " ".join(sorted(set(pairs)))
            self._update_input_buttons()
            popup.dismiss()

        self._add_button_grid(body, [
            ("从剪贴板导入", import_clip),
            ("删除末组", remove_last),
            ("清空全部", lambda *_: (pairs.clear(), buffer.__setitem__("text", ""), refresh())),
            ("确定", commit),
            ("取消", lambda *_: popup.dismiss()),
        ], cols=2, height=52)
        refresh()
        popup.open()

    def _open_pair_mode_editor(self, index):
        target = self._input_widgets[index]
        popup, body = self._popup_shell(self._input_titles[index])
        self._add_label(body, "选择两位命中模式，点击后直接保存。", height=48)

        def choose(value):
            target.text = value
            self._update_input_buttons()
            popup.dismiss()

        self._add_button_grid(body, [
            ("至少2对命中", lambda *_: choose("至少2对")),
            ("恰好2对命中", lambda *_: choose("恰好2对")),
            ("三对全命中", lambda *_: choose("三对全命中")),
            ("取消", lambda *_: popup.dismiss()),
        ], cols=1, height=56)
        popup.open()

    def _open_digit_select_editor(self, index):
        target = self._input_widgets[index]
        popup, body = self._popup_shell(self._input_titles[index])
        selected = {c for c in target.text if c.isdigit()}
        status = self._add_label(body, "", height=55, font_size="15sp")
        buttons = {}

        grid = GridLayout(cols=5, spacing=dp(5), size_hint_y=None, height=dp(105))
        for d in "0123456789":
            b = Button(text=d, font_size="16sp")
            buttons[d] = b
            def toggle(_btn, x=d):
                if x in selected:
                    selected.remove(x)
                else:
                    selected.add(x)
                refresh()
            b.bind(on_release=toggle)
            grid.add_widget(b)
        body.add_widget(grid)

        def refresh():
            for d, b in buttons.items():
                b.text = ("✓ " if d in selected else "") + d
            status.text = "已选数字：" + (" ".join(sorted(selected)) if selected else "暂无")

        def commit(*_):
            if not selected:
                self._show_message("没有数字", "请至少选择1个数字。")
                return
            target.text = "".join(sorted(selected))
            self._update_input_buttons()
            popup.dismiss()

        self._add_button_grid(body, [
            ("清空", lambda *_: (selected.clear(), refresh())),
            ("确定", commit),
            ("取消", lambda *_: popup.dismiss()),
        ], cols=3, height=52)
        refresh()
        popup.open()

    def _open_digit_filter_mode_editor(self, index):
        target = self._input_widgets[index]
        popup, body = self._popup_shell(self._input_titles[index])
        lines = [x.strip() for x in target.text.splitlines() if x.strip()]
        state = {
            "match": "全部" if lines and "全部" in lines[0] else "任意",
            "action": "去掉" if len(lines) > 1 and "去" in lines[1] else "筛出",
        }
        status = self._add_label(body, "", height=55, font_size="15sp")
        mbuttons, abuttons = {}, {}

        self._add_label(body, "判断方式", height=36)
        g1 = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(52))
        for v in ("任意", "全部"):
            b = Button(text=v)
            mbuttons[v] = b
            b.bind(on_release=lambda _b, x=v: (state.__setitem__("match", x), refresh()))
            g1.add_widget(b)
        body.add_widget(g1)

        self._add_label(body, "操作方式", height=36)
        g2 = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(52))
        for v in ("筛出", "去掉"):
            b = Button(text=v)
            abuttons[v] = b
            b.bind(on_release=lambda _b, x=v: (state.__setitem__("action", x), refresh()))
            g2.add_widget(b)
        body.add_widget(g2)

        def refresh():
            for v,b in mbuttons.items():
                b.text = ("✓ " if state["match"] == v else "") + v
            for v,b in abuttons.items():
                b.text = ("✓ " if state["action"] == v else "") + v
            status.text = f"当前：{state['match']} + {state['action']}"

        def commit(*_):
            target.text = state["match"] + "\n" + state["action"]
            self._update_input_buttons()
            popup.dismiss()

        self._add_button_grid(body, [
            ("确定", commit),
            ("取消", lambda *_: popup.dismiss()),
        ], cols=2, height=54)
        refresh()
        popup.open()

    def _open_split_button_editor(self, index):
        """3-7位：数字按钮逐组添加，或从剪贴板导入；最终仍只输出合并去重结果。"""
        target = self._input_widgets[index]
        popup, body = self._popup_shell(self._input_titles[index])
        groups = parse_split_inputs(target.text)
        buffer = {"text": ""}
        status = self._add_label(body, "", height=105, font_size="14sp")

        def refresh():
            shown = "、".join(groups[:18])
            if len(groups) > 18:
                shown += "……"
            status.text = (
                f"当前组：{buffer['text'] or '未输入'}（3-7位）\n"
                f"已添加 {len(groups)} 组：{shown or '暂无'}"
            )

        def add_digit(d):
            if len(buffer["text"]) < 7:
                buffer["text"] += d
            refresh()

        specs = [(d, lambda _b, x=d: add_digit(x)) for d in "0123456789"]
        self._add_button_grid(body, specs, cols=5, height=50)

        def add_group(*_):
            s = buffer["text"]
            if not (3 <= len(s) <= 7):
                self._show_message("位数不对", "每组必须是3-7位数字。")
                return
            groups.append(s)
            buffer["text"] = ""
            refresh()

        def import_clip(*_):
            clip = Clipboard.paste() or ""
            found = parse_split_inputs(clip)
            if not found:
                self._show_message("剪贴板没有3-7位数字", "请先复制3-7位数字，例如：345 4567 1234567。")
                return
            groups[:] = found
            buffer["text"] = ""
            refresh()

        def commit(*_):
            if buffer["text"]:
                if 3 <= len(buffer["text"]) <= 7:
                    groups.append(buffer["text"])
                    buffer["text"] = ""
                else:
                    self._show_message("当前组未完成", "当前组必须是3-7位数字，或者先点“退一位/清空当前”。")
                    return
            if not groups:
                self._show_message("没有数据", "请至少添加1组3-7位数字。")
                return
            target.text = "\n".join(groups)
            self._update_input_buttons()
            popup.dismiss()

        self._add_button_grid(body, [
            ("添加本组", add_group),
            ("退一位", lambda *_: (buffer.__setitem__("text", buffer["text"][:-1]), refresh())),
            ("清空当前", lambda *_: (buffer.__setitem__("text", ""), refresh())),
            ("删除末组", lambda *_: (groups.pop() if groups else None, refresh())),
            ("从剪贴板导入", import_clip),
            ("清空全部", lambda *_: (groups.clear(), buffer.__setitem__("text", ""), refresh())),
            ("确定", commit),
            ("取消", lambda *_: popup.dismiss()),
        ], cols=2, height=52)
        refresh()
        popup.open()

    def _open_kivy_input_editor(self, index):
        """桌面/非Android备用输入窗口。"""
        target = self._input_widgets[index]
        title = self._input_titles[index]
        hint = self._input_hints[index]

        outer = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(8)
        )

        help_label = Label(
            text=(hint or title),
            size_hint_y=None,
            height=dp(58),
            halign="left",
            valign="middle",
            font_size="14sp"
        )
        help_label.bind(
            size=lambda inst, val: setattr(inst, "text_size", (val[0], None))
        )
        outer.add_widget(help_label)

        editor = MobileTextInput(
            text=target.text,
            hint_text=hint,
            multiline=True,
            size_hint_y=1,
            font_size="19sp",
            padding=[dp(14), dp(14), dp(14), dp(14)]
        )
        outer.add_widget(editor)

        row = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        ok = Button(text="确定", font_size="17sp")
        clear = Button(text="清空输入", font_size="16sp")
        cancel = Button(text="取消", font_size="16sp")
        row.add_widget(ok)
        row.add_widget(clear)
        row.add_widget(cancel)
        outer.add_widget(row)

        pop = Popup(
            title=title,
            content=outer,
            size_hint=(0.97, 0.78),
            auto_dismiss=False
        )

        def commit(*_):
            target.text = editor.text
            editor.focus = False
            self._update_input_buttons()
            pop.dismiss()

        def clear_editor(*_):
            editor.text = ""
            editor.focus = True

        def cancel_edit(*_):
            editor.focus = False
            pop.dismiss()

        ok.bind(on_release=commit)
        clear.bind(on_release=clear_editor)
        cancel.bind(on_release=cancel_edit)
        pop.open()
        Clock.schedule_once(lambda _dt: setattr(editor, "focus", True), 0.18)

    @mainthread
    def _apply_native_input_value(self, index, value):
        """从 Android UI 线程安全地把输入值写回 Kivy 数据容器。"""
        try:
            self._input_widgets[index].text = value
            self._update_input_buttons()
        finally:
            # 释放 Java 回调引用；此时系统对话框已经关闭。
            self._native_dialog_refs = None

    @run_on_ui_thread
    def _open_native_input_editor(self, index):
        """
        Android 系统原生输入窗口。

        关键点：实际可编辑控件是 android.widget.EditText，
        不再让 Kivy TextInput 处理点击、焦点和三星中文输入法事件。
        """
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        AlertDialogBuilder = autoclass("android.app.AlertDialog$Builder")
        EditText = autoclass("android.widget.EditText")
        InputType = autoclass("android.text.InputType")
        Gravity = autoclass("android.view.Gravity")
        Context = autoclass("android.content.Context")
        InputMethodManager = autoclass("android.view.inputmethod.InputMethodManager")
        WindowManagerLayoutParams = autoclass("android.view.WindowManager$LayoutParams")
        JavaString = autoclass("java.lang.String")

        activity = PythonActivity.mActivity
        target = self._input_widgets[index]
        title = self._input_titles[index]
        hint = self._input_hints[index]

        editor = EditText(activity)
        editor.setText(JavaString(target.text or ""))
        editor.setHint(JavaString(hint or title))
        editor.setSingleLine(False)
        editor.setMinLines(7)
        editor.setMaxLines(14)
        editor.setGravity(Gravity.TOP | Gravity.START)
        editor.setHorizontallyScrolling(False)
        editor.setPadding(32, 24, 32, 24)
        editor.setTextSize(18.0)
        editor.setInputType(
            InputType.TYPE_CLASS_TEXT
            | InputType.TYPE_TEXT_FLAG_MULTI_LINE
            | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        )
        try:
            editor.setSelectAllOnFocus(False)
        except Exception:
            pass

        def commit_native():
            try:
                value = str(editor.getText().toString())
            except Exception:
                value = ""
            self._apply_native_input_value(index, value)

        def cancel_native():
            # 不改原值，只释放引用。
            self._native_dialog_refs = None

        positive = _DialogClickListener(commit_native)
        negative = _DialogClickListener(cancel_native)

        builder = AlertDialogBuilder(activity)
        builder.setTitle(JavaString(title))
        builder.setView(editor)
        builder.setPositiveButton(JavaString("确定"), positive)
        builder.setNegativeButton(JavaString("取消"), negative)

        dialog = builder.create()

        # 保留引用，避免 PyJNIus listener 在对话框关闭前被垃圾回收。
        self._native_dialog_refs = {
            "dialog": dialog,
            "editor": editor,
            "positive": positive,
            "negative": negative,
        }

        dialog.show()

        try:
            window = dialog.getWindow()
            window.setSoftInputMode(
                WindowManagerLayoutParams.SOFT_INPUT_STATE_ALWAYS_VISIBLE
                | WindowManagerLayoutParams.SOFT_INPUT_ADJUST_RESIZE
            )
        except Exception:
            pass

        # 原生 EditText 直接请求焦点并显式唤起三星/Android系统键盘。
        try:
            editor.requestFocus()
            editor.setSelection(editor.length())
            imm = activity.getSystemService(Context.INPUT_METHOD_SERVICE)
            imm.showSoftInput(editor, InputMethodManager.SHOW_IMPLICIT)
        except Exception:
            pass

    def on_mode_change(self, _spinner, mode):
        self._unfocus_inputs()
        self._reset_file_roles()
        self.current_exports = {}
        self.current_view_name = None
        self.summary.text = ""
        self.result.text = ""
        self.result_selector.values = ()
        self.result_selector.text = "选择查看结果"

        for widget in self._input_widgets:
            widget.text = ""

        config = {
            "口径1取号": (
                1, False,
                "输入口径1条件，可多行，例如：899百个",
                "", ""
            ),
            "形态取号": (
                1, False,
                "大小和奇偶一起输入，可自由混合，例如：大大大 大大小\n奇奇奇 奇奇偶",
                "", ""
            ),
            "口径1双条件全量交集": (
                2, False,
                "条件A，例如：818十个",
                "条件B，例如：881十个",
                ""
            ),
            "口径1交集后数字形态轨": (
                3, False,
                "母号A条件，例如：983十个",
                "母号B条件，例如：938十个",
                "第1行数字389；后续4行形态"
            ),
            "交集 / 不交集": (
                0, True,
                "", "", ""
            ),
            "A分别与多个文件交集": (
                0, True,
                "", "", ""
            ),
            "合并去重": (
                0, True,
                "", "", ""
            ),
            "形态筛选": (
                2, True,
                "输入要去掉的大小形态，可为空",
                "输入要去掉的奇偶形态，可为空",
                ""
            ),
            "二同 / 三同 / 三不同": (
                0, True,
                "", "", ""
            ),
            "两位组合命中筛选（按附件）": (
                2, True,
                "输入两位组合，如：01 03 05 06 ...",
                "输入模式：至少2对 / 恰好2对 / 三对全命中",
                ""
            ),
            "两位组合命中筛选（000-999）": (
                2, False,
                "输入两位组合，如：01 03 05 06 ...",
                "输入模式：至少2对 / 恰好2对 / 三对全命中",
                ""
            ),
            "数字包含 / 去除筛选": (
                2, True,
                "输入数字，例如：8 或 368",
                "第1行：任意/全部；第2行：筛出/去掉",
                ""
            ),
            "三至七位拆两位组合": (
                1, False,
                "输入3-7位数字，可多组；最终只输出全部合并去重结果",
                "", ""
            ),
            "半顺以上筛选": (
                0, True,
                "", "", ""
            ),
        }

        input_count, need_file, h1, h2, h3 = config[mode]
        self._input_hints = [h1, h2, h3]
        self._input_titles = self._mode_input_titles(mode)

        extra = ""
        if mode == "交集 / 不交集":
            extra = " 分别选择A附件、B附件。"
        elif mode == "A分别与多个文件交集":
            extra = " 先选择A，再添加B/C/D附件。"
        elif mode == "合并去重":
            extra = " 添加2个以上附件，不区分角色。"
        elif input_count:
            extra = " 点击下面的大输入按钮，弹窗会自动打开键盘。"

        self.instructions.text = "本次只使用当前输入和当前附件。" + extra

        for i, btn in enumerate(self.input_buttons):
            show = i < input_count
            btn.height = dp(60) if show else 0
            btn.opacity = 1 if show else 0
            btn.disabled = not show
            self._input_widgets[i].hint_text = self._input_hints[i]

        self._update_input_buttons()
        self._configure_file_controls(mode, need_file)



    def clear_all(self, *_):
        self._unfocus_inputs()
        for widget in self._input_widgets:
            widget.text = ""
        self._update_input_buttons()
        self._reset_file_roles()

        need_file = self.mode.text in {
            "交集 / 不交集",
            "A分别与多个文件交集",
            "合并去重",
            "形态筛选",
            "二同 / 三同 / 三不同",
            "两位组合命中筛选（按附件）",
            "数字包含 / 去除筛选",
            "半顺以上筛选",
        }
        self._configure_file_controls(self.mode.text, need_file)

        self.summary.text = ""
        self.result.text = ""
        self.current_exports = {}
        self.current_view_name = None
        self.result_selector.values = ()
        self.result_selector.text = "选择查看结果"



    def open_files(self, *_):
        """
        兼容入口：
        - 交集/不交集：缺A先选A，缺B再选B
        - A分别与多个文件交集：缺A先选A，否则追加B/C/D
        - 合并去重：追加附件
        - 其他附件功能：选择单个附件
        """
        mode = self.mode.text
        if mode == "交集 / 不交集":
            target = "A" if self.file_A is None else "B"
        elif mode == "A分别与多个文件交集":
            target = "A" if self.file_A is None else "others"
        elif mode == "合并去重":
            target = "append"
        else:
            target = "single"
        self.select_file_role(target)




    def _reset_file_roles(self):
        self.loaded_files = []
        self.file_A = None
        self.file_B = None
        self.file_single = None
        self.file_others = []
        self._append_uri_keys = set()
        self._picker_target = "single"
        self.files_label.text = "未选择附件"

    def _sync_loaded_files(self):
        mode = self.mode.text

        if mode == "交集 / 不交集":
            self.loaded_files = [
                p for p in (self.file_A, self.file_B)
                if p is not None
            ]
            return

        if mode == "A分别与多个文件交集":
            self.loaded_files = (
                ([self.file_A] if self.file_A else [])
                + list(self.file_others)
            )
            return

        if mode == "合并去重":
            self.loaded_files = list(self.file_others)
            return

        self.loaded_files = [self.file_single] if self.file_single else []

    def _configure_file_controls(self, mode, need_file):
        self.file_button_row.clear_widgets()

        if not need_file:
            self.file_row.height = 0
            self.file_row.opacity = 0
            self.file_row.disabled = True
            return

        self.file_row.height = dp(116)
        self.file_row.opacity = 1
        self.file_row.disabled = False

        def make_button(label, callback):
            b = Button(text=label, font_size="15sp")
            b.bind(on_release=callback)
            return b

        if mode == "交集 / 不交集":
            self.file_button_row.add_widget(
                make_button("选择A附件", lambda *_: self.select_file_role("A"))
            )
            self.file_button_row.add_widget(
                make_button("选择B附件", lambda *_: self.select_file_role("B"))
            )

        elif mode == "A分别与多个文件交集":
            self.file_button_row.add_widget(
                make_button("选择A附件", lambda *_: self.select_file_role("A"))
            )
            self.file_button_row.add_widget(
                make_button("添加B/C/D附件", lambda *_: self.select_file_role("others"))
            )

        elif mode == "合并去重":
            self.file_button_row.add_widget(
                make_button("添加附件", lambda *_: self.select_file_role("append"))
            )

        else:
            self.file_button_row.add_widget(
                make_button("选择TXT附件", lambda *_: self.select_file_role("single"))
            )

        self._refresh_loaded_files_label()

    def select_file_role(self, target):
        self._unfocus_inputs()
        self._picker_target = target

        if platform == "android":
            try:
                self._open_android_file_picker()
            except Exception as e:
                self._show_message(
                    "附件选择失败",
                    f"无法打开系统文件选择器：\n{e}"
                )
            return

        self._open_desktop_file_picker(target)

    def _open_desktop_file_picker(self, target):
        chooser = FileChooserListView(
            path=os.path.expanduser("~"),
            filters=["*.txt"],
            multiselect=target in {"others", "append"}
        )

        box = BoxLayout(orientation="vertical")
        box.add_widget(chooser)

        row = BoxLayout(size_hint_y=None, height=dp(48))
        ok = Button(text="确定")
        cancel = Button(text="取消")
        row.add_widget(ok)
        row.add_widget(cancel)
        box.add_widget(row)

        pop = Popup(
            title="选择TXT附件",
            content=box,
            size_hint=(0.95, 0.9)
        )

        def choose(*_args):
            chosen = chooser.selection[:]
            if chosen:
                self._assign_selected_paths(target, chosen)
            pop.dismiss()

        ok.bind(on_release=choose)
        cancel.bind(on_release=lambda *_a: pop.dismiss())
        pop.open()

    def _assign_selected_paths(self, target, paths):
        valid = [p for p in paths if p]
        if not valid:
            return

        if target == "A":
            self.file_A = valid[0]

        elif target == "B":
            self.file_B = valid[0]

        elif target == "single":
            self.file_single = valid[0]

        elif target in {"others", "append"}:
            for p in valid:
                if p not in self.file_others:
                    self.file_others.append(p)

        self._sync_loaded_files()
        self._refresh_loaded_files_label()


    def _attachment_policy(self):
        mode = self.mode.text

        if mode == "交集 / 不交集":
            return "exact", 2

        if mode in {"A分别与多个文件交集", "合并去重"}:
            return "minimum", 2

        if mode in {
            "形态筛选",
            "二同 / 三同 / 三不同",
            "两位组合命中筛选（按附件）",
            "数字包含 / 去除筛选",
            "半顺以上筛选",
        }:
            return "single", 1

        return "single", 1

    def _apply_selected_paths(self, paths):
        """非Android/已是本地路径时，也遵循相同的附件累计规则。"""
        valid = [p for p in paths if p]
        if not valid:
            return

        policy, limit = self._attachment_policy()

        if policy == "single":
            self.loaded_files = [valid[0]]
            return

        if policy == "exact":
            remain = max(0, limit - len(self.loaded_files))
            if remain:
                self.loaded_files.extend(valid[:remain])
            return

        # minimum：持续追加，并按路径去重
        for p in valid:
            if p not in self.loaded_files:
                self.loaded_files.append(p)

    def _attachment_status_text(self):
        n = len(self.loaded_files)
        mode = self.mode.text
        policy, limit = self._attachment_policy()

        if policy == "single":
            return f"当前已选择 {n} 个附件。" if n else "尚未选择附件。"

        if policy == "exact":
            if n >= limit:
                return f"附件已齐：{n}/{limit}。可以开始分析。"
            return f"当前 {n}/{limit}，还需要选择 {limit - n} 个附件。"

        # minimum
        if n >= limit:
            return f"当前已选择 {n} 个附件，可以开始分析；还可以继续追加。"
        return f"当前已选择 {n} 个附件，至少还需要 {limit - n} 个。"


    def _open_android_file_picker(self):
        from jnius import autoclass
        from android import activity as android_activity

        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")

        if not getattr(self, "_android_picker_bound", False):
            android_activity.bind(
                on_activity_result=self._on_android_activity_result
            )
            self._android_picker_bound = True

        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("text/plain")

        # B/C/D 和合并去重允许系统多选；
        # A、B、单附件模式只取一个，角色最清楚。
        allow_multiple = self._picker_target in {"others", "append"}
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, allow_multiple)
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

        PythonActivity.mActivity.startActivityForResult(intent, 9047)

    @mainthread

    @mainthread
    def _on_android_activity_result(self, request_code, result_code, data):
        if request_code != 9047:
            return

        try:
            from jnius import autoclass

            Activity = autoclass("android.app.Activity")
            if result_code != Activity.RESULT_OK or data is None:
                return

            uris = []
            clip = data.getClipData()

            if clip is not None:
                for i in range(clip.getItemCount()):
                    uri = clip.getItemAt(i).getUri()
                    if uri is not None:
                        uris.append(uri)
            else:
                uri = data.getData()
                if uri is not None:
                    uris.append(uri)

            if not uris:
                self._show_message(
                    "附件选择",
                    "没有读取到任何TXT附件。"
                )
                return

            target = self._picker_target
            imported = []
            errors = []
            skipped = 0

            # A/B/单附件：只使用第一个能正常读取的TXT
            if target in {"A", "B", "single"}:
                for i, uri in enumerate(uris, start=1):
                    try:
                        path = self._copy_android_uri_to_local(uri, i)
                        imported = [path]
                        break
                    except Exception as e:
                        errors.append(f"第{i}个附件：{e}")

                if imported:
                    path = imported[0]
                    if target == "A":
                        self.file_A = path
                        role_name = "A"
                    elif target == "B":
                        self.file_B = path
                        role_name = "B"
                    else:
                        self.file_single = path
                        role_name = "当前"

                    self._sync_loaded_files()
                    self._refresh_loaded_files_label()

                    nums = self.read_file(path)
                    self._show_message(
                        "附件已读取",
                        f"{role_name}附件：{os.path.basename(path)}\n"
                        f"识别到 {len(nums)} 注。"
                    )
                else:
                    self._show_message(
                        "附件读取失败",
                        "没有任何附件能够读取。\n"
                        + "\n".join(errors)
                    )
                return

            # B/C/D 或合并去重：允许一次或多次追加。
            for i, uri in enumerate(uris, start=1):
                uri_key = str(uri)

                if uri_key in self._append_uri_keys:
                    skipped += 1
                    continue

                try:
                    path = self._copy_android_uri_to_local(
                        uri,
                        len(self.file_others) + len(imported) + 1
                    )
                    imported.append((uri_key, path))
                except Exception as e:
                    errors.append(f"第{i}个附件：{e}")

            for uri_key, path in imported:
                self.file_others.append(path)
                self._append_uri_keys.add(uri_key)

            self._sync_loaded_files()
            self._refresh_loaded_files_label()

            details = []
            for _uri_key, path in imported:
                details.append(
                    f"{os.path.basename(path)}："
                    f"{len(self.read_file(path))}注"
                )

            msg = ""
            if target == "others":
                roles = []
                for idx, path in enumerate(self.file_others, start=1):
                    role = chr(65 + idx)   # 1->B, 2->C, 3->D
                    roles.append(f"{role}={os.path.basename(path)}")
                msg = "当前角色：\n"
                msg += (
                    f"A={os.path.basename(self.file_A)}\n"
                    if self.file_A else
                    "A=未选择\n"
                )
                msg += "\n".join(roles) if roles else "B/C/D尚未选择"
            else:
                msg = f"当前已添加 {len(self.file_others)} 个附件。"

            if details:
                msg += "\n\n本次新增：\n" + "\n".join(details)
            if skipped:
                msg += f"\n\n已忽略重复附件 {skipped} 个。"
            if errors:
                msg += "\n\n未能读取：\n" + "\n".join(errors)

            self._show_message("附件已读取", msg)

        except Exception as e:
            self._show_message("附件读取失败", str(e))

    def _android_uri_display_name(self, resolver, uri, fallback):
        try:
            OpenableColumns = __import__("jnius").autoclass("android.provider.OpenableColumns")
            cursor = resolver.query(uri, None, None, None, None)
            if cursor is not None:
                try:
                    idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if idx >= 0 and cursor.moveToFirst():
                        name = cursor.getString(idx)
                        if name:
                            return str(name)
                finally:
                    cursor.close()
        except Exception:
            pass
        return fallback

    def _copy_android_uri_to_local(self, uri, index):
        """
        把 content:// URI 内容复制到 App 自己的 imports 目录。
        TXT通常只有几KB，逐字节读取足够稳定，且不依赖外部存储权限。
        """
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        resolver = PythonActivity.mActivity.getContentResolver()

        name = self._android_uri_display_name(
            resolver,
            uri,
            f"附件_{index}.txt"
        )
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        if not name.lower().endswith(".txt"):
            name += ".txt"

        import_dir = os.path.join(
            App.get_running_app().user_data_dir,
            "imports"
        )
        os.makedirs(import_dir, exist_ok=True)

        # 避免多个同名附件互相覆盖。
        base, ext = os.path.splitext(name)
        out_path = os.path.join(import_dir, name)
        suffix = 1
        while os.path.exists(out_path):
            out_path = os.path.join(import_dir, f"{base}_{suffix}{ext}")
            suffix += 1

        stream = resolver.openInputStream(uri)
        if stream is None:
            raise RuntimeError("无法打开附件")

        try:
            with open(out_path, "wb") as f:
                while True:
                    b = stream.read()
                    if b == -1:
                        break
                    f.write(bytes((b & 0xFF,)))
        finally:
            try:
                stream.close()
            except Exception:
                pass

        # 立刻验证是否能解析到三位组合，避免“选到了但后续得到0注”。
        nums = self.read_file(out_path)
        if not nums:
            try:
                os.remove(out_path)
            except Exception:
                pass
            raise RuntimeError("TXT中没有识别到三位组合")

        return out_path



    def _refresh_loaded_files_label(self):
        mode = self.mode.text

        if mode == "交集 / 不交集":
            a = os.path.basename(self.file_A) if self.file_A else "未选择"
            b = os.path.basename(self.file_B) if self.file_B else "未选择"
            self.files_label.text = f"A={a}\nB={b}"
            return

        if mode == "A分别与多个文件交集":
            lines = [
                "A=" + (
                    os.path.basename(self.file_A)
                    if self.file_A else
                    "未选择"
                )
            ]

            for i, path in enumerate(self.file_others, start=1):
                role = chr(65 + i)  # B/C/D...
                lines.append(f"{role}={os.path.basename(path)}")

            if len(lines) > 4:
                shown = lines[:4]
                shown.append(f"……共 {len(lines)} 个角色附件")
                lines = shown

            self.files_label.text = "；".join(lines)
            return

        if mode == "合并去重":
            if not self.file_others:
                self.files_label.text = "未选择附件"
            else:
                names = [os.path.basename(p) for p in self.file_others]
                shown = "、".join(names[:2])
                if len(names) > 2:
                    shown += "……"
                self.files_label.text = (
                    f"已选 {len(names)} 个附件：{shown}"
                )
            return

        if self.file_single:
            self.files_label.text = (
                "已选：" + os.path.basename(self.file_single)
            )
        else:
            self.files_label.text = "未选择附件"

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
        # do_* 在调用本方法前，self.result.text 中已经写好了统计、闭环和组合。
        raw = self.result.text
        self.current_exports = named
        names = list(named.keys())

        summary = self._summary_only(raw)
        if names:
            result_list = "\n".join(f"{i+1}. {name}" for i, name in enumerate(names))
            summary = (summary + "\n\n可查看/保存的结果：\n" + result_list).strip()
        self.summary.text = summary

        self.result_selector.values = names

        if names:
            self.current_view_name = names[0]
            self.result_selector.text = names[0]
            self.show_result(names[0])
        else:
            self.current_view_name = None
            self.result_selector.text = "选择查看结果"


    def on_result_selected(self, _spinner, name):
        if name in self.current_exports:
            self.current_view_name = name
            self.show_result(name)


    def show_result(self, name):
        values = self.current_exports.get(name)
        if values is None:
            return

        if isinstance(values, str):
            body = values
            vals = re.findall(r"(?<!\d)(?:\d{2}|\d{3})(?!\d)", values)
            count = len(vals)
            unit = "组" if vals and all(len(x) == 2 for x in vals) else "注"
        else:
            vals = sorted(set(values))
            body = "\n".join(
                " ".join(vals[i:i + 10])
                for i in range(0, len(vals), 10)
            ) if vals else "（无）"
            count = len(vals)
            unit = "组" if vals and all(len(x) == 2 for x in vals) else "注"

        self.result.text = f"【{name}】 共 {count} {unit}\n\n{body}"
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
        """稳定保存TXT到公共 Download/数字分析工具 目录。"""
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        BuildVersion = autoclass("android.os.Build$VERSION")
        Environment = autoclass("android.os.Environment")
        activity = PythonActivity.mActivity

        # 先在App私有目录生成一个临时TXT，确保Python写文件本身稳定。
        cache_dir = os.path.join(App.get_running_app().user_data_dir, "export_cache")
        os.makedirs(cache_dir, exist_ok=True)
        private_file = os.path.join(cache_dir, filename)
        with open(private_file, "w", encoding="utf-8-sig") as f:
            f.write(content)

        if BuildVersion.SDK_INT >= 29:
            # Android 10+：使用官方 MediaStore。
            # 注意：PyJNIus访问Java嵌套类必须用 $，不能用 MediaStore.MediaColumns。
            MediaStoreDownloads = autoclass("android.provider.MediaStore$Downloads")
            ContentValues = autoclass("android.content.ContentValues")
            FileInputStream = autoclass("java.io.FileInputStream")
            FileUtils = autoclass("android.os.FileUtils")

            resolver = activity.getContentResolver()

            # 直接使用 Android ContentResolver 的标准列名，避免不同ROM下嵌套类常量反射失败。
            values = ContentValues()
            values.put("_display_name", filename)
            values.put("mime_type", "text/plain")
            values.put(
                "relative_path",
                Environment.DIRECTORY_DOWNLOADS + "/数字分析工具"
            )

            uri = resolver.insert(MediaStoreDownloads.EXTERNAL_CONTENT_URI, values)
            if uri is None:
                raise RuntimeError("无法在手机下载目录创建TXT文件")

            out_stream = resolver.openOutputStream(uri)
            if out_stream is None:
                raise RuntimeError("无法打开手机下载文件")

            in_stream = FileInputStream(private_file)
            try:
                FileUtils.copy(in_stream, out_stream)
                out_stream.flush()
            finally:
                try:
                    in_stream.close()
                except Exception:
                    pass
                try:
                    out_stream.close()
                except Exception:
                    pass

            return "Download/数字分析工具/" + filename

        # Android 9及以下：直接写公共Download目录。
        base = Environment.getExternalStoragePublicDirectory(
            Environment.DIRECTORY_DOWNLOADS
        ).getAbsolutePath()
        folder = os.path.join(base, "数字分析工具")
        os.makedirs(folder, exist_ok=True)
        public_file = os.path.join(folder, filename)

        with open(private_file, "rb") as src_f, open(public_file, "wb") as dst_f:
            dst_f.write(src_f.read())

        return public_file

    def _clipboard_copy(self, text):
        if not text:
            self._show_message("复制失败", "当前没有可复制的内容。")
            return
        try:
            Clipboard.copy(text)
            self._show_message("复制成功", "结果已经复制到系统剪贴板。")
        except Exception as e:
            self._show_message("复制失败", str(e))

    def copy_current_result(self, *_):
        name = self.current_view_name
        if not name or name not in self.current_exports:
            self._show_message("复制失败", "请先选择一个结果。")
            return

        values = self.current_exports[name]
        if isinstance(values, str):
            body = values
        else:
            body = format_txt(values)

        text = f"【{name}】\n{body}"
        self._clipboard_copy(text)

    def copy_all_results(self, *_):
        if not self.current_exports:
            self._show_message("复制失败", "当前没有可复制的结果。")
            return

        blocks = []
        for name, values in self.current_exports.items():
            if isinstance(values, str):
                body = values
            else:
                body = format_txt(values)
            blocks.append(f"【{name}】\n{body}")

        self._clipboard_copy("\n\n".join(blocks))

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
        self._unfocus_inputs()
        mode = self.mode.text
        self.current_exports = {}
        self.current_view_name = None
        self.summary.text = ""
        self.result.text = ""
        self.result_selector.values = ()
        self.result_selector.text = "选择查看结果"

        try:
            fn = getattr(self, "do_" + str(MODES.index(mode) + 1))
            fn()

            # 正常分析函数会调用 set_exports；错误信息则直接显示。
            if not self.current_exports and self.result.text:
                self.summary.text = self.result.text
                Clock.schedule_once(self._scroll_result_top, 0)

        except Exception as e:
            self.summary.text = "运行失败"
            self.result.text = f"运行出错：{e}"
            Clock.schedule_once(self._scroll_result_top, 0)

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
        text_all = self.input1.text or ""
        size_selected = [x for x in SIZE_SHAPES if x in text_all]
        parity_selected = [x for x in PARITY_SHAPES if x in text_all]

        if not size_selected:
            self.result.text = "请至少输入1个有效的大小形态。"
            return
        if not parity_selected:
            self.result.text = "请至少输入1个有效的奇偶形态。"
            return

        full = [
            n for n in ALL_NUMBERS
            if size_shape(n) in size_selected and parity_shape(n) in parity_selected
        ]
        same23 = [n for n in full if repeat_type(n) != "三不同"]
        diff = [n for n in full if repeat_type(n) == "三不同"]

        self.result.text = "\n".join([
            "输入方式：大小和奇偶共用一个输入框",
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
        mode = self.mode.text

        if mode == "交集 / 不交集":
            if not self.file_A or not self.file_B:
                self.result.text = (
                    "请先分别选择A附件和B附件。"
                )
                return False

        elif mode == "A分别与多个文件交集":
            if not self.file_A or not self.file_others:
                self.result.text = (
                    "请先选择A附件，并至少添加1个B/C/D附件。"
                )
                return False

        elif mode == "合并去重":
            if len(self.file_others) < 2:
                self.result.text = (
                    f"至少需要2个TXT附件，目前 {len(self.file_others)} 个。"
                )
                return False

        else:
            if count == 1 and not self.file_single:
                self.result.text = "请先选择1个TXT附件。"
                return False

        self._sync_loaded_files()
        n = len(self.loaded_files)

        if count is not None and n != count:
            self.result.text = (
                f"需要选择 {count} 个TXT附件，目前 {n} 个。"
            )
            return False

        if minimum is not None and n < minimum:
            self.result.text = (
                f"至少需要选择 {minimum} 个TXT附件，目前 {n} 个。"
            )
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

        merged = set()
        for t in tokens:
            merged.update(split_to_pairs(t))

        merged = sorted(merged)
        self.result.text = pair_section_text("合并去重结果", merged)
        self.set_exports(**{
            f"三至七位拆两位_合并去重_{len(merged)}组": merged
        })

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
        return NumberAnalysisRoot()


if __name__ == "__main__":
    NumberAnalysisApp().run()
