"""
services/notation_gen.py
Генерация изображений нотного стана (скрипичный ключ) с одной нотой для тренировки
чтения нот с листа ("нотная грамота").

Рисуем стан программно через matplotlib — без внешних API и без готовых картинок.
Поддерживаемый диапазон: от C3 (две добавочные линейки снизу) до A5 (добавочные линейки сверху),
что покрывает типичный материал для начинающих и среднего уровня.
"""
import asyncio
import matplotlib
matplotlib.use("Agg")  # без GUI-бэкенда — важно для сервера без дисплея
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Позиция ноты на стане задаётся в "шагах" от нижней линии стана (E4 = 0).
# Каждый шаг — это полступени между линией и соседним промежутком (диатонический шаг).
# Считаем от E4 (первая снизу линия скрипичного ключа) вверх по белым клавишам.
_STEP_ORDER = ["C", "D", "E", "F", "G", "A", "B"]

# Референс: E4 находится на нижней линии стана (позиция 0).
_REFERENCE_NOTE = "E"
_REFERENCE_OCTAVE = 4


def _note_step_position(note_name: str) -> float:
    """
    Переводит имя ноты (например 'C4', 'F#5') в вертикальную позицию на стане
    в диатонических шагах относительно E4 (нижняя линия = 0).
    Диезы/бемоли не сдвигают позицию по высоте на стане (только влияют на альтерацию,
    для упрощения в MVP используем только натуральные ноты для нотного стана).
    """
    pitch = note_name[0]
    octave = int(note_name[-1])
    pitch_idx = _STEP_ORDER.index(pitch)
    ref_idx = _STEP_ORDER.index(_REFERENCE_NOTE)

    steps_within_octave = pitch_idx - ref_idx
    steps_from_octaves = (octave - _REFERENCE_OCTAVE) * 7
    return steps_within_octave + steps_from_octaves


# Диапазон нот для упражнений на чтение с листа (только натуральные ноты для ясности)
NOTATION_RANGE = [
    "C3", "D3", "E3", "F3", "G3", "A3", "B3",
    "C4", "D4", "E4", "F4", "G4", "A4", "B4",
    "C5", "D5", "E5", "F5", "G5", "A5",
]


def _draw_treble_clef(ax, x: float, staff_bottom_y: float, line_spacing: float) -> None:
    """
    Рисует упрощённый (стилизованный) скрипичный ключ из простых фигур,
    так как большинство системных шрифтов не содержат нужный музыкальный юникод-символ.
    """
    cx = x
    # нижний завиток
    ax.add_patch(patches.Circle((cx, staff_bottom_y - line_spacing * 0.3), line_spacing * 0.55,
                                 fill=False, linewidth=2.2, color="black"))
    # верхняя петля
    ax.add_patch(patches.Circle((cx, staff_bottom_y + line_spacing * 3.2), line_spacing * 0.9,
                                 fill=False, linewidth=2.2, color="black"))
    # вертикальный "хвост", проходящий через весь стан
    ax.plot([cx, cx], [staff_bottom_y - line_spacing * 1.3, staff_bottom_y + line_spacing * 5.2],
            color="black", linewidth=2.2)
    # маленькая точка-узел снизу (стилизация)
    ax.add_patch(patches.Circle((cx, staff_bottom_y - line_spacing * 1.3), line_spacing * 0.12,
                                 fill=True, color="black"))


def _render_staff_with_note_sync(note_name: str) -> str:
    """Синхронная (тяжёлая) отрисовка PNG. Выполняется в отдельном потоке."""
    fig, ax = plt.subplots(figsize=(5, 3), dpi=150)
    ax.set_xlim(0, 10)
    ax.set_ylim(-4, 6)
    ax.axis("off")
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    line_spacing = 0.5
    staff_bottom_y = 0.0  # E4 — нижняя линия

    # 5 линий стана
    for i in range(5):
        y = staff_bottom_y + i * line_spacing
        ax.plot([1.2, 9.2], [y, y], color="black", linewidth=1.3)

    _draw_treble_clef(ax, x=1.9, staff_bottom_y=staff_bottom_y, line_spacing=line_spacing)

    # позиция ноты
    step_pos = _note_step_position(note_name)
    note_y = staff_bottom_y + step_pos * (line_spacing / 2)
    note_x = 6.0

    # добавочные линейки, если нота выходит за пределы стана
    top_line_y = staff_bottom_y + 4 * line_spacing
    bottom_line_y = staff_bottom_y
    if note_y > top_line_y:
        y = top_line_y + line_spacing
        while y <= note_y + 1e-6:
            ax.plot([note_x - 0.35, note_x + 0.35], [y, y], color="black", linewidth=1.3)
            y += line_spacing
    elif note_y < bottom_line_y:
        y = bottom_line_y - line_spacing
        while y >= note_y - 1e-6:
            ax.plot([note_x - 0.35, note_x + 0.35], [y, y], color="black", linewidth=1.3)
            y -= line_spacing

    # головка ноты (эллипс, слегка наклонённый — как в классической нотации)
    ax.add_patch(patches.Ellipse((note_x, note_y), width=0.55, height=0.38, angle=20,
                                  facecolor="black", edgecolor="black"))

    # штиль (вертикальная палочка) — вверх, если нота ниже середины стана, иначе вниз
    middle_y = staff_bottom_y + 2 * line_spacing
    if note_y < middle_y:
        ax.plot([note_x + 0.27, note_x + 0.27], [note_y, note_y + 1.7], color="black", linewidth=1.4)
    else:
        ax.plot([note_x - 0.27, note_x - 0.27], [note_y, note_y - 1.7], color="black", linewidth=1.4)

    from utils.media import temp_path
    out_path = temp_path("staff", ".png")
    plt.tight_layout(pad=0.3)
    fig.savefig(out_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out_path


async def render_staff_with_note(note_name: str) -> str:
    """Асинхронная точка входа: рисует нотный стан с одной нотой, возвращает путь к PNG."""
    return await asyncio.to_thread(_render_staff_with_note_sync, note_name)
