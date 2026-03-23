from __future__ import annotations

from dataclasses import asdict, dataclass
from textwrap import dedent


@dataclass(frozen=True)
class PptPresetStyle:
    id: str
    name_zh: str
    name_en: str
    color: str
    description_zh: str
    description_en: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


PRESET_STYLES: dict[str, PptPresetStyle] = {
    "minimal-business": PptPresetStyle(
        id="minimal-business",
        name_zh="极简商务",
        name_en="Minimal Business",
        color="#1A1A2E",
        description_zh=dedent(
            """
            视觉描述：全局视觉语言对标国际顶级咨询公司的演示规范，强调专业、克制与信息优先。
            整体采用极致扁平化与强秩序网格，以清晰传达为唯一优先级。禁止渐变、发光、拟物纹理
            与任何非必要装饰。光照环境固定为均匀漫射光：无方向性主光、无硬阴影，保持干净透亮。

            配色与材质：背景色全篇锁定为深炭灰（#1A1A2E），标题与正文固定为纯白（#FFFFFF）。
            唯一强调色为冷蓝（#3B82F6），仅用于关键数字、关键结论关键词，使用面积不超过单页
            总面积3%。分割线与辅助标注使用浅灰（#E5E7EB）。材质表现为平滑矢量色块，不使用
            纸张纹理、噪点或复杂材质。全稿默认不使用阴影。

            内容与排版：版式遵循严格模块化网格，所有元素按统一对齐规则排布。页面结构固定为
            几何分区：标题区、主图/图表区、要点区、结论区；分区边界使用1px细线划分。字体固定
            为无衬线体系，标题粗体，正文常规/细体。同一层级禁止混用不同字体家族。大量留白，
            黑白灰为主色调，点缀一个强调色，适合正式商务汇报、投资路演等高端场景。

            插图与图表规则：所有视觉素材必须为矢量插画形式，统一白色线稿，关键部件用强调色
            点亮。禁止彩色照片、写实渲染。图表必须为2D扁平矢量，无渐变无立体效果。

            渲染要求：超高清矢量插画与商务信息图风格，文字与图形边缘锐利无锯齿，整体呈现
            严谨的企业级商务美学。
            """
        ).strip(),
        description_en=dedent(
            """
            Visual: Global visual language aligns with top-tier consulting presentation standards,
            emphasizing professionalism, restraint, and information-first design. Extreme flat design
            with strong ordered grids. No gradients, glows, skeuomorphic textures, or decorative elements.
            Uniform diffused studio lighting — no hard shadows, clean and calm.

            Colors & Materials: Background locked to dark charcoal (#1A1A2E). All text in pure white
            (#FFFFFF). Single accent color: cool blue (#3B82F6), used only for key numbers and
            conclusions, covering no more than 3% of page area. Dividers in light gray (#E5E7EB).
            Smooth vector color blocks only — no textures, grain, or complex materials. No shadows.

            Typography: Strict modular grid system. Geometric page partitions with 1px thin-line
            dividers. Sans-serif font system. Generous whitespace, black-white-gray palette with
            one accent. Ideal for formal business reports, investor pitches, and executive briefings.

            Illustrations & Charts: Vector illustrations only — white line art with accent highlights.
            No photos or realistic rendering. 2D flat vector charts, no gradients or 3D effects.

            Rendering: Ultra-HD vector illustration and business infographic style. Sharp edges,
            clean lines, stable hierarchy — rigorous enterprise-level business aesthetics.
            """
        ).strip(),
    ),
    "tech-future": PptPresetStyle(
        id="tech-future",
        name_zh="科技未来",
        name_en="Tech Future",
        color="#7C3AED",
        description_zh=dedent(
            """
            视觉描述：全局视觉语言融合赛博朋克与现代SaaS产品的未来感。整体氛围深邃且富有动感，
            仿佛置身于高科技的数据中心或虚拟空间。光照采用暗调环境下的自发光效果，模拟霓虹灯管
            和激光的辉光。深色背景配合蓝紫渐变，几何线条与数据可视化元素贯穿全稿。

            配色与材质：背景色采用深邃的午夜黑（#0B0F19），以衬托前景亮度。主色调使用高饱和度的
            电光蓝（#00A3FF）与赛博紫（#7C3AED）进行线性渐变，营造流动的能量感。材质大量运用
            半透明玻璃、发光网格线以及带有金属光泽的几何体。

            内容与排版：画面中包含悬浮的3D几何元素（立方体、四面体或芯片结构），带有线框渲染效果。
            排版倾向不对称的动态平衡，使用科技感的等宽字体或现代无衬线体。背景可隐约添加电路板纹理、
            数据流或点阵图作为装饰。适合科技公司、AI主题、产品发布等场景。

            渲染要求：Octane Render渲染风格，强调光线追踪、辉光（Bloom）效果和景深控制，呈现
            精细的粒子特效和充满科技张力的视觉冲击力。
            """
        ).strip(),
        description_en=dedent(
            """
            Visual: Global visual language blends cyberpunk with modern SaaS futurism. Deep, dynamic
            atmosphere as if inside a high-tech data center or virtual space. Self-luminous effects
            in dark environments, simulating neon tubes and laser glow. Dark backgrounds with
            blue-purple gradients, geometric lines, and data visualization throughout.

            Colors & Materials: Background in deep Midnight Black (#0B0F19). Primary palette uses
            high-saturation Electric Blue (#00A3FF) and Cyber Purple (#7C3AED) in linear gradients
            for a flowing energy feel. Materials feature translucent glass, glowing grid lines,
            and metallic-sheen geometric shapes.

            Typography: Floating 3D geometric elements with wireframe rendering. Asymmetric dynamic
            balance layout. Tech-feel monospace or modern sans-serif fonts. Background may include
            circuit board textures, data streams, or dot-matrix patterns. Ideal for tech companies,
            AI themes, and product launches.

            Rendering: Octane Render style with ray tracing, bloom effects, and depth of field control.
            Refined particle effects with tech-driven visual impact.
            """
        ).strip(),
    ),
    "creative-fun": PptPresetStyle(
        id="creative-fun",
        name_zh="活泼创意",
        name_en="Creative Fun",
        color="#FF6A00",
        description_zh=dedent(
            """
            视觉描述：全局视觉语言像一个充满活力的初创公司 Pitch Deck 或创意工作坊。整体氛围
            轻松、愉悦、充满想象力，打破常规束缚。光照明亮且充满阳光感，色彩之间没有阴影，
            呈现彻底的扁平化。高饱和度色彩搭配手绘元素和不规则形状，适合创意提案、品牌营销、
            面向年轻受众的场景。

            配色与材质：背景色使用高明度的暖黄色（#FFD54A）。配色方案极其大胆，混合使用鲜艳的
            活力橙（#FF6A00）、草绿（#22C55E）和天蓝（#38BDF8），形成孟菲斯（Memphis）风格的
            撞色效果。材质上模拟手绘涂鸦、剪纸或粗糙边缘的矢量插画。

            内容与排版：画面包含手绘风格的插图元素，如涂鸦箭头、星星、波浪线和不规则有机形状
            色块。排版允许文字倾斜、重叠或跳跃，打破僵硬网格。字体选用圆润可爱的圆体或手写体。
            可在角落放置拟人化的可爱物体或夸张的对话气泡。

            渲染要求：Dribbble热门插画风格，色彩鲜艳平涂，线条流畅富有弹性，给人快乐、友好且
            极具亲和力的感觉。
            """
        ).strip(),
        description_en=dedent(
            """
            Visual: Global visual language resembles an energetic startup pitch deck or creative
            workshop. Relaxed, joyful, and imaginative atmosphere breaking conventional constraints.
            Bright, sunny lighting with no shadows — completely flat design. High-saturation colors
            with hand-drawn elements and irregular shapes. Ideal for creative proposals, brand
            marketing, and young audiences.

            Colors & Materials: Background in high-brightness Warm Yellow (#FFD54A). Bold color scheme
            mixing Vibrant Orange (#FF6A00), Grass Green (#22C55E), and Sky Blue (#38BDF8) for
            Memphis-style color clashing. Materials simulate hand-drawn doodles, paper cutouts,
            or rough-edged vector illustrations.

            Typography: Hand-drawn illustration elements — doodle arrows, stars, wavy lines, and
            irregular organic shapes. Text may be tilted, overlapping, or bouncing, breaking rigid
            grids. Rounded bubble fonts or handwritten styles. Anthropomorphic cute objects or
            exaggerated speech bubbles in corners.

            Rendering: Dribbble trending illustration style with vivid flat colors, smooth elastic
            lines, conveying a happy, friendly, and approachable feeling.
            """
        ).strip(),
    ),
    "infographic": PptPresetStyle(
        id="infographic",
        name_zh="信息图表",
        name_en="Infographic",
        color="#0EA5E9",
        description_zh=dedent(
            """
            视觉描述：全局视觉语言借鉴顶级数据新闻与信息图表设计，强调数据可视化、图标丰富和
            信息层次。整体以清晰展示复杂信息为目标，适合数据报告、行业分析、复杂概念解释。
            光照采用极柔和的均匀漫反射，保持图表与文字的绝对清晰。

            配色与材质：背景色为极浅的冰白色（#F8FAFC），保证图表与数据的高可读性。主色调使用
            天蓝（#0EA5E9）作为主要数据色，搭配琥珀橙（#F59E0B）作为对比/警示色，薄荷绿
            （#10B981）作为正向/增长色。辅助灰（#94A3B8）用于次要信息与坐标轴。材质为纯净的
            矢量平面，追求印刷级的精确与干净。

            内容与排版：核心设计元素包括：流程图、对比表格、时间线、数据仪表盘、图标矩阵和
            统计卡片。每页以一个核心数据洞察为中心，辅以迷你图表和关键指标 (KPI) 卡片。版式
            采用模块化网格，信息密度高但层次分明。大量使用简洁的线性图标（line icons）辅助
            信息传达。字体使用现代无衬线体，数字部分使用等宽字体突出数据。

            图表规则：优先使用柱状图、折线图、环形图和树状图。图表配色遵循主色+对比色+辅助灰
            的三级体系。数据标签精简，图例从简，网格线使用虚线且极淡。所有图表2D扁平，禁止3D
            效果和过度装饰。

            渲染要求：高清信息图表风格，追求《经济学人》《纽约时报》级别的数据可视化美学。
            线条精细锐利，色彩克制但层次丰富，整体呈现专业、可信、易读的数据叙事风格。
            """
        ).strip(),
        description_en=dedent(
            """
            Visual: Global visual language draws from top-tier data journalism and infographic design,
            emphasizing data visualization, rich iconography, and information hierarchy. Focused on
            clearly presenting complex information. Ideal for data reports, industry analysis, and
            complex concept explanations. Soft uniform diffused lighting for absolute chart and
            text clarity.

            Colors & Materials: Background in ice white (#F8FAFC) for maximum chart readability.
            Primary data color: sky blue (#0EA5E9), with amber orange (#F59E0B) for contrast/alerts,
            mint green (#10B981) for positive/growth indicators. Auxiliary gray (#94A3B8) for
            secondary info and axes. Pure vector flat materials with print-level precision.

            Typography: Core design elements include flowcharts, comparison tables, timelines,
            data dashboards, icon matrices, and stat cards. Each page centers on one core data
            insight, supported by mini-charts and KPI cards. Modular grid layout with high
            information density but clear hierarchy. Extensive use of clean line icons. Modern
            sans-serif fonts, with monospace for numerical data emphasis.

            Charts: Prefer bar charts, line charts, donut charts, and treemaps. Three-tier chart
            color system: primary + contrast + auxiliary gray. Minimal data labels, simplified
            legends, ultra-light dashed grid lines. All charts 2D flat — no 3D effects.

            Rendering: HD infographic style targeting The Economist / New York Times-level data
            visualization aesthetics. Fine sharp lines, restrained but layered colors, presenting
            professional, trustworthy, and readable data narrative style.
            """
        ).strip(),
    ),
}

DEFAULT_PRESET_STYLE_ID = "minimal-business"


def get_preset_style(style_id: str | None) -> PptPresetStyle:
    resolved = (style_id or DEFAULT_PRESET_STYLE_ID).strip() or DEFAULT_PRESET_STYLE_ID
    return PRESET_STYLES.get(resolved, PRESET_STYLES[DEFAULT_PRESET_STYLE_ID])


def list_preset_styles() -> list[dict[str, str]]:
    return [style.to_dict() for style in PRESET_STYLES.values()]
