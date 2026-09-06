from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp


class NumberAnalysisApp(App):

    def build(self):
        self.title = "数字分析工具"

        root = BoxLayout(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(12)
        )

        title = Label(
            text="数字分析工具",
            font_size="30sp",
            size_hint_y=None,
            height=dp(70)
        )

        subtitle = Label(
            text="Android 离线版 V1 测试",
            font_size="18sp",
            size_hint_y=None,
            height=dp(50)
        )

        root.add_widget(title)
        root.add_widget(subtitle)

        scroll = ScrollView()

        menu = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None,
            padding=[0, dp(10)]
        )

        menu.bind(
            minimum_height=menu.setter("height")
        )

        functions = [
            "口径1取号",
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
            "半顺以上筛选",
        ]

        for name in functions:

            btn = Button(
                text=name,
                font_size="17sp",
                size_hint_y=None,
                height=dp(55)
            )

            btn.bind(
                on_release=self.show_test_message
            )

            menu.add_widget(btn)

        scroll.add_widget(menu)
        root.add_widget(scroll)

        self.status = Label(
            text="离线计算核心将在下一步加入",
            font_size="16sp",
            size_hint_y=None,
            height=dp(55)
        )

        root.add_widget(self.status)

        return root

    def show_test_message(self, button):
        self.status.text = (
            "已点击："
            + button.text
            + "\nAPK界面运行正常"
        )


if __name__ == "__main__":
    NumberAnalysisApp().run()
