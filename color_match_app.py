"""
图片颜色相似度查找应用
功能：上传图片，点击选择位置，显示颜色最相近的几个位置及相似程度
"""

import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw
import numpy as np
from colormath.color_objects import LabColor, sRGBColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000
import cv2


class ColorSimilarityApp:
    def __init__(self, root):
        self.root = root
        self.root.title("图片颜色相似度查找器 / Color Similarity Finder")
        self.root.geometry("1200x800")

        # 变量
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.photo = None
        self.image_array = None
        self.lab_image = None
        self.click_x = None
        self.click_y = None
        self.similar_locations = []

        # 参数控制
        self.num_similar = 3  # 显示相似位置数量
        self.min_distance = 20  # 最小像素间距（避免聚集）

        # 缩放和平移状态
        self.zoom_level = 1.0  # 当前缩放级别
        self.pan_x = 0  # X轴平移偏移量
        self.pan_y = 0  # Y轴平移偏移量
        self.pan_start = None  # 拖拽起始位置
        self.is_grabbing = False  # 是否正在抓手拖动

        # 取样模式
        self.sample_mode = 'point'  # 取样模式：'point'=点击取样, 'circle'=圆形取样
        self.circle_start = None  # 圆形取样的起始点
        self.circle_id = None  # 圆形的canvas ID
        self.circle_rect = None  # 圆形区域信息

        # 对比区域（限制搜索范围）
        self.comparison_start = None  # 对比区域选择起始点
        self.comparison_rect = None  # 对比区域（屏幕坐标）
        self.comparison_rect_original = None  # 对比区域（原图坐标）
        self.comparison_id = None  # 对比区域矩形ID
        self.comparison_lasso_points = []  # 对比区域套索路径点
        self.comparison_lasso_lines = []  # 对比区域套索线段ID列表

        self.setup_ui()

    def setup_ui(self):
        """设置UI界面"""
        # 顶部控制面板
        control_frame = tk.Frame(self.root, padx=10, pady=10, bg='#f0f0f0')
        control_frame.pack(side=tk.TOP, fill=tk.X)

        # 上传按钮
        tk.Button(control_frame, text="📁 上传图片 Upload", command=self.upload_image,
                 font=('Arial', 12), bg='#4CAF50', fg='white', padx=20).pack(side=tk.LEFT, padx=5)

        # 相似数量设置
        tk.Label(control_frame, text="相似位置数量 Count:", bg='#f0f0f0', font=('Arial', 10)).pack(side=tk.LEFT, padx=5)
        self.num_entry = tk.Entry(control_frame, width=5, font=('Arial', 10))
        self.num_entry.insert(0, "3")
        self.num_entry.pack(side=tk.LEFT, padx=5)
        self.num_entry.bind('<Return>', self.update_settings)

        # 最小间距设置
        tk.Label(control_frame, text="最小间距 Min Dist:", bg='#f0f0f0', font=('Arial', 10)).pack(side=tk.LEFT, padx=5)
        self.min_dist_entry = tk.Entry(control_frame, width=5, font=('Arial', 10))
        self.min_dist_entry.insert(0, str(self.min_distance))
        self.min_dist_entry.pack(side=tk.LEFT, padx=5)
        self.min_dist_entry.bind('<Return>', self.update_settings)

        # 应用设置按钮
        tk.Button(control_frame, text="设置生效 Apply", command=self.update_settings,
                 font=('Arial', 10)).pack(side=tk.LEFT, padx=5)

        # 第一列：清除标记和重置视图
        action_frame = tk.Frame(control_frame, bg='#f0f0f0')
        action_frame.pack(side=tk.LEFT, padx=5)
        tk.Button(action_frame, text="🗑️\n清除标记\nClear Markers", command=self.clear_markers,
                 font=('Arial', 9), bg='#f44336', fg='white').pack(side=tk.LEFT, padx=2)
        tk.Button(action_frame, text="🔄\n重置视图\nReset View", command=self.reset_view,
                 font=('Arial', 9), bg='#2196F3', fg='white').pack(side=tk.LEFT, padx=2)

        # 第二列：取样模式（竖排）
        sample_mode_frame = tk.Frame(control_frame, bg='#f0f0f0')
        sample_mode_frame.pack(side=tk.LEFT, padx=5)
        tk.Label(sample_mode_frame, text="取样模式\nSample Mode", bg='#f0f0f0', font=('Arial', 9)).pack(side=tk.LEFT, padx=2)
        self.sample_mode_var = tk.StringVar(value='point')
        tk.Radiobutton(sample_mode_frame, text="点击\nPoint", variable=self.sample_mode_var,
                      value='point', command=self.change_sample_mode, bg='#f0f0f0', font=('Arial', 9)).pack(side=tk.LEFT, padx=2)
        tk.Radiobutton(sample_mode_frame, text="圆形\nCircle", variable=self.sample_mode_var,
                      value='circle', command=self.change_sample_mode, bg='#f0f0f0', font=('Arial', 9)).pack(side=tk.LEFT, padx=2)

        # 说明标签
        tk.Label(control_frame, text="操作提示 Tips: 点击取样 Click to sample | Shift+左键绘制搜索范围 Shift+Left-drag search area | Ctrl+左键平移 Ctrl+Left-drag pan | 滚轮缩放 Wheel zoom",
                bg='#f0f0f0', font=('Arial', 8), fg='#666').pack(side=tk.LEFT, padx=20)

        # 主内容区域
        content_frame = tk.Frame(self.root)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧：图片显示区域
        self.canvas_frame = tk.Frame(content_frame, bg='#ddd', bd=2, relief=tk.SUNKEN)
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.canvas_frame, bg='white', cursor='crosshair')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        # 绑定左键按下事件
        self.canvas.bind('<ButtonPress-1>', self.on_left_button_press)
        # 绑定左键释放事件
        self.canvas.bind('<ButtonRelease-1>', self.on_left_button_release)
        # 绑定左键拖动事件
        self.canvas.bind('<B1-Motion>', self.on_left_button_drag)
        # 绑定鼠标滚轮事件（Windows和macOS）
        self.canvas.bind('<MouseWheel>', self.on_zoom)  # Windows
        self.canvas.bind('<Button-4>', self.on_zoom)    # Linux scroll up
        self.canvas.bind('<Button-5>', self.on_zoom)    # Linux scroll down
        # 绑定拖拽平移事件（右键）
        self.canvas.bind('<ButtonPress-3>', self.on_pan_start)  # 右键按下
        self.canvas.bind('<B3-Motion>', self.on_pan_move)       # 右键拖动
        # 绑定按键事件来检测 Ctrl 键
        self.canvas.bind('<KeyPress>', self.on_key_press)
        self.canvas.bind('<KeyRelease>', self.on_key_release)

        # 右侧：结果列表
        self.result_frame = tk.Frame(content_frame, width=300, bg='#f9f9f9')
        self.result_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(10, 0))
        self.result_frame.pack_propagate(False)

        tk.Label(self.result_frame, text="相似颜色位置 Similar Colors", font=('Arial', 14, 'bold'),
                bg='#f9f9f9').pack(pady=10)

        # 结果文本框
        self.result_text = tk.Text(self.result_frame, font=('Courier New', 9),
                                   wrap=tk.WORD, padx=10, pady=10)
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 滚动条
        scrollbar = tk.Scrollbar(self.result_text)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.result_text.yview)

    def update_settings(self, event=None):
        """更新设置参数"""
        try:
            self.num_similar = int(self.num_entry.get())
            self.min_distance = int(self.min_dist_entry.get())
            if self.image_array is not None and self.click_x is not None:
                self.find_similar_colors(self.click_x, self.click_y)
        except ValueError:
            messagebox.showerror("错误 Error", "请输入有效的数字 Please enter valid numbers")

    def change_sample_mode(self):
        """切换取样模式"""
        self.sample_mode = self.sample_mode_var.get()
        # 清除正在绘制的圆形
        if self.circle_id:
            self.canvas.delete(self.circle_id)
            self.circle_id = None
        self.circle_start = None
        self.circle_rect = None

    def upload_image(self):
        """上传图片"""
        file_types = [
            ("图片文件 Image Files", "*.jpg *.jpeg *.png *.bmp *.gif"),
            ("所有文件 All Files", "*.*")
        ]

        path = filedialog.askopenfilename(filetypes=file_types)
        if path:
            self.image_path = path
            self.load_image()

    def load_image(self):
        """加载并显示图片"""
        try:
            # 使用PIL打开图片
            self.original_image = Image.open(self.image_path)

            # 转换为RGB模式
            if self.original_image.mode != 'RGB':
                self.original_image = self.original_image.convert('RGB')

            # 转换为numpy数组
            self.image_array = np.array(self.original_image)

            # 预计算Lab颜色空间（用于更准确的颜色差异计算）
            rgb_array = self.image_array.astype(np.float32) / 255.0
            self.lab_image = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2LAB)

            # 调整显示尺寸
            self.display_image_on_canvas()

            # 清除之前的标记
            self.clear_markers()

        except Exception as e:
            messagebox.showerror("错误 Error", f"无法加载图片 Cannot load image: {str(e)}")

    def on_zoom(self, event):
        """处理鼠标滚轮缩放事件"""
        if self.original_image is None:
            return

        # 获取画布尺寸
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # 确定缩放因子
        if event.num == 5 or event.delta < 0:
            # 向下滚动，缩小
            factor = 0.9
        else:
            # 向上滚动，放大
            factor = 1.1

        # 计算新的缩放级别
        new_zoom = self.zoom_level * factor

        # 限制缩放范围（0.1倍到10倍）
        if new_zoom < 0.1 or new_zoom > 10:
            return

        # 鼠标在画布上的位置
        mouse_x = event.x
        mouse_y = event.y

        # 计算缩放前图片的中心位置
        old_center_x = canvas_width // 2 + self.pan_x
        old_center_y = canvas_height // 2 + self.pan_y

        # 鼠标相对于图片中心的偏移
        offset_from_center_x = mouse_x - old_center_x
        offset_from_center_y = mouse_y - old_center_y

        # 更新缩放级别
        self.zoom_level = new_zoom

        # 调整平移，使鼠标下的图片点保持不变
        # 新的偏移 = 旧的偏移 * 缩放比例
        scale_ratio = factor if factor > 1 else 1 / factor
        self.pan_x -= offset_from_center_x * (scale_ratio - 1)
        self.pan_y -= offset_from_center_y * (scale_ratio - 1)

        # 重新显示图片
        self.display_image_on_canvas()

    def on_pan_start(self, event):
        """开始拖拽平移"""
        if self.original_image is None:
            return
        self.pan_start = (event.x, event.y)

    def on_pan_move(self, event):
        """拖拽平移中"""
        if self.original_image is None or self.pan_start is None:
            return

        dx = event.x - self.pan_start[0]
        dy = event.y - self.pan_start[1]

        self.pan_x += dx
        self.pan_y += dy

        self.pan_start = (event.x, event.y)
        self.display_image_on_canvas()

    def on_key_press(self, event):
        """按键按下"""
        if event.keysym in ('Control_L', 'Control_R'):
            self.canvas.config(cursor='fleur')

    def on_key_release(self, event):
        """按键释放"""
        if event.keysym in ('Control_L', 'Control_R'):
            if not self.is_grabbing:
                self.canvas.config(cursor='crosshair')

    def on_left_button_press(self, event):
        """左键按下"""
        if self.original_image is None:
            return

        # 检查是否按住了 Ctrl 键（Ctrl键优先级最高，用于平移）
        if event.state & 0x4:  # Ctrl 键的掩码
            self.is_grabbing = True
            self.pan_start = (event.x, event.y)
            return

        # 检查是否按住了 Shift 键（用于绘制搜索范围套索）
        if event.state & 0x1:  # Shift 键的掩码
            self.comparison_start = (event.x, event.y)
            self.comparison_lasso_points = [(event.x, event.y)]
            # 清除之前的搜索范围套索
            for line_id in self.comparison_lasso_lines:
                self.canvas.delete(line_id)
            self.comparison_lasso_lines = []
            return

        # 圆形取样模式
        if self.sample_mode == 'circle':
            self.circle_start = (event.x, event.y)
            # 清除之前的圆形
            if self.circle_id:
                self.canvas.delete(self.circle_id)
            # 创建新的圆形（初始为点）
            self.circle_id = self.canvas.create_oval(
                event.x, event.y, event.x, event.y,
                outline='red', width=2
            )
            return

    def on_left_button_release(self, event):
        """左键释放"""
        # 搜索范围套索选择结束
        if self.comparison_start:
            self.on_search_area_selection_end(event)
            self.comparison_start = None
            return

        # 圆形取样结束
        if self.sample_mode == 'circle' and self.circle_start:
            self.on_circle_sample_end(event)
            self.circle_start = None
            return

        # 如果不是Ctrl平移，则是普通点击取样
        if not self.is_grabbing:
            # 直接点击取样
            self.on_image_click(event)

        self.is_grabbing = False
        self.pan_start = None

    def on_left_button_drag(self, event):
        """左键拖动"""
        if self.original_image is None:
            return

        # Ctrl + 左键拖动平移
        if self.is_grabbing and self.pan_start is not None:
            dx = event.x - self.pan_start[0]
            dy = event.y - self.pan_start[1]
            self.pan_x += dx
            self.pan_y += dy
            self.pan_start = (event.x, event.y)
            self.display_image_on_canvas()
            return

        # 搜索范围套索绘制（Shift+左键）
        if self.comparison_start:
            new_point = (event.x, event.y)
            last_point = self.comparison_lasso_points[-1]
            distance = ((new_point[0] - last_point[0])**2 + (new_point[1] - last_point[1])**2)**0.5
            if distance > 5:
                self.comparison_lasso_points.append(new_point)
                line_id = self.canvas.create_line(
                    last_point[0], last_point[1],
                    new_point[0], new_point[1],
                    fill='cyan', width=2
                )
                self.comparison_lasso_lines.append(line_id)
            return

        # 圆形取样拖动
        if self.sample_mode == 'circle' and self.circle_start:
            start_x, start_y = self.circle_start
            current_x, current_y = event.x, event.y

            # 计算圆心（按下位置和当前位置的中点）
            center_x = (start_x + current_x) / 2
            center_y = (start_y + current_y) / 2

            # 计算半径（两点距离的一半）
            radius = ((current_x - start_x)**2 + (current_y - start_y)**2)**0.5 / 2

            if self.circle_id:
                self.canvas.coords(
                    self.circle_id,
                    center_x - radius, center_y - radius,
                    center_x + radius, center_y + radius
                )
            self.circle_rect = {
                'center_x': center_x,
                'center_y': center_y,
                'radius': radius
            }
            return

    def redraw_lasso(self):
        """重新绘制套索区域"""
        if not hasattr(self, 'search_lasso_points_original'):
            return

        # 清除旧的套索线
        for line_id in self.comparison_lasso_lines:
            self.canvas.delete(line_id)
        self.comparison_lasso_lines = []

        # 将原图坐标转换为屏幕坐标并重新绘制
        for i in range(len(self.search_lasso_points_original)):
            orig_x, orig_y = self.search_lasso_points_original[i]
            screen_x = self.display_offset_x + orig_x * self.scale
            screen_y = self.display_offset_y + orig_y * self.scale

            if i > 0:
                prev_orig_x, prev_orig_y = self.search_lasso_points_original[i-1]
                prev_screen_x = self.display_offset_x + prev_orig_x * self.scale
                prev_screen_y = self.display_offset_y + prev_orig_y * self.scale

                line_id = self.canvas.create_line(
                    prev_screen_x, prev_screen_y,
                    screen_x, screen_y,
                    fill='cyan', width=2
                )
                self.comparison_lasso_lines.append(line_id)

        # 闭合路径
        if len(self.search_lasso_points_original) > 0:
            first_orig_x, first_orig_y = self.search_lasso_points_original[0]
            last_orig_x, last_orig_y = self.search_lasso_points_original[-1]
            first_screen_x = self.display_offset_x + first_orig_x * self.scale
            first_screen_y = self.display_offset_y + first_orig_y * self.scale
            last_screen_x = self.display_offset_x + last_orig_x * self.scale
            last_screen_y = self.display_offset_y + last_orig_y * self.scale

            line_id = self.canvas.create_line(
                last_screen_x, last_screen_y,
                first_screen_x, first_screen_y,
                fill='cyan', width=2
            )
            self.comparison_lasso_lines.append(line_id)

    def display_image_on_canvas(self):
        """在画布上显示图片"""
        if self.original_image is None:
            return

        # 获取画布尺寸
        self.canvas.update()
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            self.root.after(100, self.display_image_on_canvas)
            return

        # 计算基础缩放比例（适应画布）
        img_width, img_height = self.original_image.size
        scale_w = canvas_width / img_width
        scale_h = canvas_height / img_height
        base_scale = min(scale_w, scale_h) * 0.95

        # 应用用户缩放级别
        self.scale = base_scale * self.zoom_level

        # 调整图片大小
        new_width = int(img_width * self.scale)
        new_height = int(img_height * self.scale)
        self.display_image = self.original_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 计算图片位置（考虑平移）
        # 默认居中，然后应用平移
        center_x = canvas_width // 2 + self.pan_x
        center_y = canvas_height // 2 + self.pan_y

        # 显示图片
        self.photo = ImageTk.PhotoImage(self.display_image)
        self.canvas.delete("all")
        self.canvas.create_image(center_x, center_y, image=self.photo, anchor=tk.CENTER)

        # 保存显示图片的信息（用于坐标转换）
        self.display_offset_x = center_x - new_width // 2
        self.display_offset_y = center_y - new_height // 2

        # 重新绘制套索区域（如果存在）
        self.redraw_lasso()

        # 重新绘制标记（如果存在）
        if self.click_x is not None or (self.sample_mode == 'circle' and hasattr(self, 'circle_center_x')):
            self.draw_markers()

    def point_in_polygon(self, x, y, polygon):
        """判断点是否在多边形内（射线法）"""
        n = len(polygon)
        inside = False
        p1x, p1y = polygon[0]
        for i in range(n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def on_search_area_selection_end(self, event):
        """搜索范围选择结束（套索）"""
        if len(self.comparison_lasso_points) < 3:
            return

        # 闭合路径
        first_point = self.comparison_lasso_points[0]
        last_point = self.comparison_lasso_points[-1]
        line_id = self.canvas.create_line(
            last_point[0], last_point[1],
            first_point[0], first_point[1],
            fill='cyan', width=2
        )
        self.comparison_lasso_lines.append(line_id)

        # 转换为原图坐标
        img_height, img_width = self.image_array.shape[:2]
        original_lasso_points = []
        for px, py in self.comparison_lasso_points:
            orig_x = int((px - self.display_offset_x) / self.scale)
            orig_y = int((py - self.display_offset_y) / self.scale)
            orig_x = max(0, min(orig_x, img_width - 1))
            orig_y = max(0, min(orig_y, img_height - 1))
            original_lasso_points.append((orig_x, orig_y))

        # 保存搜索范围套索路径（套索区域会一直保留）
        self.search_lasso_points_original = original_lasso_points

        # 如果已经有点击位置或圆形取样，立即重新查找
        if self.click_x is not None and self.click_y is not None:
            self.find_similar_colors(self.click_x, self.click_y)
        elif self.sample_mode == 'circle' and hasattr(self, 'circle_center_x'):
            self.find_similar_colors_by_circle(self.circle_center_x, self.circle_center_y, self.circle_radius)

    def on_circle_sample_end(self, event):
        """圆形取样结束"""
        if not hasattr(self, 'circle_rect') or self.circle_rect is None:
            return

        rect = self.circle_rect
        radius = rect['radius']

        if radius < 5:
            return  # 圆太小，忽略

        # 转换为原图坐标
        center_x = int((rect['center_x'] - self.display_offset_x) / self.scale)
        center_y = int((rect['center_y'] - self.display_offset_y) / self.scale)
        radius_original = int(radius / self.scale)

        # 确保在图片范围内
        img_height, img_width = self.image_array.shape[:2]
        center_x = max(0, min(center_x, img_width - 1))
        center_y = max(0, min(center_y, img_height - 1))

        # 保存圆形区域信息
        self.circle_rect_original = {
            'center_x': center_x,
            'center_y': center_y,
            'radius': radius_original
        }

        # 设置 click_x 和 click_y，以便套索等其他功能能正常工作
        self.click_x = center_x
        self.click_y = center_y

        # 计算圆内平均颜色并查找相似颜色
        self.find_similar_colors_by_circle(center_x, center_y, radius_original)

    def on_image_click(self, event):
        """处理图片点击事件"""
        if self.image_array is None:
            messagebox.showinfo("提示 Info", "请先上传图片 Please upload an image first")
            return

        # 计算在原图中的坐标
        x = int((event.x - self.display_offset_x) / self.scale)
        y = int((event.y - self.display_offset_y) / self.scale)

        # 检查坐标是否在图片范围内
        img_height, img_width = self.image_array.shape[:2]
        if 0 <= x < img_width and 0 <= y < img_height:
            self.click_x = x
            self.click_y = y
            self.find_similar_colors(x, y)

    def rgb_to_lab(self, rgb):
        """将RGB颜色转换为Lab颜色空间"""
        r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
        srgb = sRGBColor(r, g, b)
        lab = convert_color(srgb, LabColor)
        return lab

    def find_similar_colors_by_circle(self, center_x, center_y, radius):
        """查找与圆形区域平均颜色相似的位置"""
        if self.image_array is None:
            return

        img_height, img_width = self.image_array.shape[:2]

        # 创建圆形mask
        y_indices, x_indices = np.ogrid[:img_height, :img_width]
        mask_circle = (y_indices - center_y) ** 2 + (x_indices - center_x) ** 2 <= radius ** 2

        # 计算圆内区域的平均颜色
        pixels_in_circle = self.image_array[mask_circle]
        if len(pixels_in_circle) == 0:
            return

        avg_color = np.mean(pixels_in_circle, axis=0)
        target_lab = self.rgb_to_lab(avg_color)
        target_lab_array = np.array([target_lab.lab_l, target_lab.lab_a, target_lab.lab_b])

        # 计算所有像素与目标颜色的差异
        diff = np.sqrt(np.sum((self.lab_image - target_lab_array) ** 2, axis=2))

        # 基础mask：排除圆形取样区域
        mask = np.ones_like(diff, dtype=bool)
        exclusion_radius = radius + self.min_distance
        mask_exclude_circle = (y_indices - center_y) ** 2 + (x_indices - center_x) ** 2 > exclusion_radius ** 2
        mask = mask & mask_exclude_circle

        # 如果有套索区域，添加套索限制
        if hasattr(self, 'search_lasso_points_original'):
            search_points = np.array(self.search_lasso_points_original, dtype=np.int32).reshape((-1, 1, 2))
            mask_in_lasso = np.zeros((img_height, img_width), dtype=np.uint8)
            cv2.fillPoly(mask_in_lasso, [search_points], 1)
            mask_in_lasso = mask_in_lasso.astype(bool)
            mask = mask & mask_in_lasso

        # 找到最相似的N个位置
        masked_diff = diff.copy()
        masked_diff[~mask] = np.inf

        # 获取最小的N个值的位置
        flat_indices = np.argpartition(masked_diff.flatten(), self.num_similar)[:self.num_similar]
        flat_indices = flat_indices[np.argsort(masked_diff.flatten()[flat_indices])]

        # 转换为坐标
        self.similar_locations = []
        for idx in flat_indices:
            flat_y, flat_x = np.unravel_index(idx, diff.shape)
            if masked_diff[flat_y, flat_x] < np.inf:
                similarity = max(0, 100 - diff[flat_y, flat_x] * 2)
                self.similar_locations.append({
                    'x': flat_x,
                    'y': flat_y,
                    'rgb': tuple(self.image_array[flat_y, flat_x]),
                    'similarity': similarity,
                    'distance': diff[flat_y, flat_x]
                })

        # 保存圆形区域标记位置（用于绘制）
        self.circle_center_x = center_x
        self.circle_center_y = center_y
        self.circle_radius = radius

        # 显示结果
        self.display_results()
        self.draw_markers()

    def find_similar_colors(self, x, y):
        """查找相似颜色位置（单点模式）"""
        if self.image_array is None:
            return

        # 检查是否有套索区域
        has_lasso = hasattr(self, 'search_lasso_points_original')

        # 获取选中的颜色
        target_rgb = self.image_array[y, x]
        target_lab = self.rgb_to_lab(target_rgb)
        target_lab_array = np.array([target_lab.lab_l, target_lab.lab_a, target_lab.lab_b])

        img_height, img_width = self.image_array.shape[:2]

        # 计算欧氏距离
        diff = np.sqrt(np.sum((self.lab_image - target_lab_array) ** 2, axis=2))

        # 基础mask：排除点击位置附近的像素
        mask = np.ones_like(diff, dtype=bool)
        center_y, center_x = y, x
        radius = self.min_distance
        y_indices, x_indices = np.ogrid[:img_height, :img_width]
        mask_from_center = (y_indices - center_y) ** 2 + (x_indices - center_x) ** 2 >= radius ** 2
        mask = mask & mask_from_center

        # 如果有套索区域，添加套索限制
        if has_lasso:
            search_points = np.array(self.search_lasso_points_original, dtype=np.int32).reshape((-1, 1, 2))
            mask_in_lasso = np.zeros((img_height, img_width), dtype=np.uint8)
            cv2.fillPoly(mask_in_lasso, [search_points], 1)
            mask_in_lasso = mask_in_lasso.astype(bool)
            mask = mask & mask_in_lasso

        # 找到最相似的N个位置
        masked_diff = diff.copy()
        masked_diff[~mask] = np.inf

        # 获取最小的N个值的位置
        flat_indices = np.argpartition(masked_diff.flatten(), self.num_similar)[:self.num_similar]
        flat_indices = flat_indices[np.argsort(masked_diff.flatten()[flat_indices])]

        # 转换为坐标
        self.similar_locations = []
        for idx in flat_indices:
            flat_y, flat_x = np.unravel_index(idx, diff.shape)
            if masked_diff[flat_y, flat_x] < np.inf:
                similarity = max(0, 100 - diff[flat_y, flat_x] * 2)
                self.similar_locations.append({
                    'x': flat_x,
                    'y': flat_y,
                    'rgb': tuple(self.image_array[flat_y, flat_x]),
                    'similarity': similarity,
                    'distance': diff[flat_y, flat_x]
                })

        # 显示结果
        self.display_results()
        self.draw_markers()

    def display_results(self):
        """显示结果到右侧面板"""
        self.result_text.delete(1.0, tk.END)

        if not self.similar_locations:
            return  # 静默返回，不显示"未找到相似位置"

        # 显示选中的颜色信息
        if self.sample_mode == 'circle' and hasattr(self, 'circle_center_x'):
            # 圆形取样模式
            pixels_in_circle = self.image_array[
                max(0, self.circle_center_y - self.circle_radius):min(self.image_array.shape[0], self.circle_center_y + self.circle_radius + 1),
                max(0, self.circle_center_x - self.circle_radius):min(self.image_array.shape[1], self.circle_center_x + self.circle_radius + 1)
            ]
            # 创建mask获取圆内像素
            y_indices, x_indices = np.ogrid[:pixels_in_circle.shape[0], :pixels_in_circle.shape[1]]
            center_offset_y = self.circle_center_y - max(0, self.circle_center_y - self.circle_radius)
            center_offset_x = self.circle_center_x - max(0, self.circle_center_x - self.circle_radius)
            mask = (y_indices - center_offset_y) ** 2 + (x_indices - center_offset_x) ** 2 <= self.circle_radius ** 2
            avg_color = tuple(np.mean(pixels_in_circle[mask], axis=0).astype(int))

            self.result_text.insert(tk.END, "=" * 40 + "\n")
            self.result_text.insert(tk.END, "⭕ 圆形取样模式 Circle Sample Mode\n")
            self.result_text.insert(tk.END, f"圆心 Center: ({self.circle_center_x}, {self.circle_center_y})\n")
            self.result_text.insert(tk.END, f"半径 Radius: {self.circle_radius}\n")
            self.result_text.insert(tk.END, f"平均颜色 Avg Color RGB: {avg_color}\n")

            if hasattr(self, 'search_lasso_points_original'):
                search_num = len(self.search_lasso_points_original)
                self.result_text.insert(tk.END, f"搜索范围 Search Range: {search_num}-point lasso area\n")
            self.result_text.insert(tk.END, "=" * 40 + "\n\n")
        else:
            # 单点取样模式
            target_rgb = self.image_array[self.click_y, self.click_x]

            if hasattr(self, 'search_lasso_points_original'):
                # 点击+搜索范围模式
                search_num = len(self.search_lasso_points_original)
                self.result_text.insert(tk.END, "=" * 40 + "\n")
                self.result_text.insert(tk.END, "🎯 点击+搜索范围模式 Click + Search Mode\n")
                self.result_text.insert(tk.END, f"取样位置 Sample Location: ({self.click_x}, {self.click_y})\n")
                self.result_text.insert(tk.END, f"取样颜色 Sample Color RGB: {tuple(target_rgb)}\n")
                self.result_text.insert(tk.END, f"搜索范围 Search Range: {search_num}-point lasso area\n")
                self.result_text.insert(tk.END, "=" * 40 + "\n\n")
            else:
                # 单点模式
                self.result_text.insert(tk.END, "=" * 40 + "\n")
                self.result_text.insert(tk.END, "📍 单点选择模式 Single Point Mode\n")
                self.result_text.insert(tk.END, f"选中的颜色 Selected Color:\n")
                self.result_text.insert(tk.END, f"  位置 Location: ({self.click_x}, {self.click_y})\n")
                self.result_text.insert(tk.END, f"  RGB: {tuple(target_rgb)}\n")
                self.result_text.insert(tk.END, "=" * 40 + "\n\n")

        # 显示相似位置
        self.result_text.insert(tk.END, f"找到 Found {len(self.similar_locations)} 个相似位置:\n\n")

        for i, loc in enumerate(self.similar_locations, 1):
            self.result_text.insert(tk.END, f"{i}. 位置 Location: ({loc['x']}, {loc['y']})\n")
            self.result_text.insert(tk.END, f"   RGB: {loc['rgb']}\n")
            self.result_text.insert(tk.END, f"   相似度 Similarity: {loc['similarity']:.1f}%\n")
            self.result_text.insert(tk.END, f"   色差 Diff: {loc['distance']:.2f}\n")
            self.result_text.insert(tk.END, "-" * 30 + "\n")

    def draw_markers(self):
        """在图片上绘制标记"""
        self.canvas.delete("marker")

        # 绘制取样区域
        if self.sample_mode == 'circle' and hasattr(self, 'circle_center_x'):
            # 圆形取样模式：绘制红色虚线圆形（和点击取样一样的颜色）
            center_screen_x = self.display_offset_x + self.circle_center_x * self.scale
            center_screen_y = self.display_offset_y + self.circle_center_y * self.scale
            radius_screen = self.circle_radius * self.scale

            self.canvas.create_oval(
                center_screen_x - radius_screen, center_screen_y - radius_screen,
                center_screen_x + radius_screen, center_screen_y + radius_screen,
                outline='red', width=3, dash=(5, 5), tags="marker"
            )
        elif self.click_x is not None:
            # 单点取样模式：绘制红色圆圈
            x1 = self.display_offset_x + self.click_x * self.scale
            y1 = self.display_offset_y + self.click_y * self.scale
            r = 8
            self.canvas.create_oval(x1-r, y1-r, x1+r, y1+r, outline='red', width=3, tags="marker")

        # 绘制相似位置（彩色圆圈）
        for i, loc in enumerate(self.similar_locations):
            x2 = self.display_offset_x + loc['x'] * self.scale
            y2 = self.display_offset_y + loc['y'] * self.scale

            # 颜色根据相似度变化
            intensity = int(255 * (1 - loc['similarity'] / 100))
            color = f'#{255:02x}{255-intensity:02x}{0:02x}'

            r2 = 6
            self.canvas.create_oval(x2-r2, y2-r2, x2+r2, y2+r2, outline=color, width=2, tags="marker")

            # 添加编号
            if i < 20:  # 只为前20个添加编号
                self.canvas.create_text(x2, y2-15, text=str(i+1), fill=color,
                                       font=('Arial', 10, 'bold'), tags="marker")

    def clear_markers(self):
        """清除所有标记"""
        self.canvas.delete("marker")
        # 清除对比区域套索
        for line_id in self.comparison_lasso_lines:
            self.canvas.delete(line_id)
        self.comparison_lasso_lines = []
        self.comparison_lasso_points = []

        # 清除圆形取样
        if self.circle_id:
            self.canvas.delete(self.circle_id)
            self.circle_id = None
        self.circle_start = None
        self.circle_rect = None

        self.similar_locations = []
        self.click_x = None
        self.click_y = None
        # 清除搜索范围数据
        if hasattr(self, 'search_lasso_points_original'):
            delattr(self, 'search_lasso_points_original')
        if hasattr(self, 'comparison_lasso_points_original'):
            delattr(self, 'comparison_lasso_points_original')
        if hasattr(self, 'comparison_rect_original'):
            delattr(self, 'comparison_rect_original')
        # 清除圆形取样数据
        if hasattr(self, 'circle_center_x'):
            delattr(self, 'circle_center_x')
        if hasattr(self, 'circle_center_y'):
            delattr(self, 'circle_center_y')
        if hasattr(self, 'circle_radius'):
            delattr(self, 'circle_radius')
        if hasattr(self, 'circle_rect_original'):
            delattr(self, 'circle_rect_original')

        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, "点击图片进行取样...\nClick on image to sample...\n")

    def reset_view(self):
        """重置视图到初始状态"""
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        if self.original_image is not None:
            self.display_image_on_canvas()
            # 如果有标记，重新绘制
            if self.click_x is not None:
                self.draw_markers()


def main():
    root = tk.Tk()
    app = ColorSimilarityApp(root)

    # 窗口居中
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')

    root.mainloop()


if __name__ == "__main__":
    main()
