from __future__ import annotations

import logging
import os
import sys
import time
from datetime import UTC, date, datetime, timedelta

from matplotlib import dates as mdates
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator, StrMethodFormatter

import store

COMMITTED_CREATED_COLOR = "#47A197"
COMMITTED_MODIFIED_COLOR = "#6F75C3"
PENDING_CREATED_COLOR = "#C25F85"
PENDING_MODIFIED_COLOR = "#C3933A"

FRAME_COLOR = "#334155"
TEXT_COLOR = "#E5E7EB"
BACKGROUND_COLOR = "#0B0F19"
AXES_COLOR = "#111827"

logger = logging.getLogger(__name__)


def _smooth_dates(date_numbers: list[float], samples_per_day: int = 12) -> list[float]:
    smoothed: list[float] = []

    for index in range(len(date_numbers) - 1):
        start = date_numbers[index]
        end = date_numbers[index + 1]

        for step in range(samples_per_day):
            smoothed.append(start + (end - start) * step / samples_per_day)

    smoothed.append(date_numbers[-1])

    return smoothed


def _smooth_values(values: list[int], samples_per_day: int = 12) -> list[float]:
    smoothed: list[float] = []
    last_index = len(values) - 1

    for index in range(last_index):
        previous = values[max(index - 1, 0)]
        current = values[index]
        following = values[index + 1]
        next_following = values[min(index + 2, last_index)]

        for step in range(samples_per_day):
            t = step / samples_per_day
            value = 0.5 * (
                2 * current
                + (-previous + following) * t
                + (2 * previous - 5 * current + 4 * following - next_following) * t**2
                + (-previous + 3 * current - 3 * following + next_following) * t**3
            )
            smoothed.append(max(value, 0.0))

    smoothed.append(float(values[-1]))

    return smoothed


def render_chart(settings: store.Settings) -> None:
    max_rowid, event_count, _ = store.get_event_totals(settings)
    rows = store.get_daily_aggregates(settings)

    daily = {
        row["day"]: (
            row["produced_created"],
            row["produced_modified"],
            row["committed_created"],
            row["committed_modified"],
        )
        for row in rows
    }

    days: list[date] = []
    first_day = date.fromisoformat(min(daily))
    last_day = date.fromisoformat(max(daily))
    current_day = first_day

    while current_day <= last_day:
        days.append(current_day)
        current_day += timedelta(days=1)

    dates = [datetime.combine(day, datetime.min.time()) for day in days]
    date_numbers = mdates.date2num(dates).tolist()
    now = datetime.now(UTC)
    day = now.day
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    updated = f"{now:%b} {day}{suffix} {now:%Y}"
    footer_text = f"Updated: {updated} | {event_count:,} events"

    produced_created: list[int] = []
    produced_modified: list[int] = []
    committed_created: list[int] = []
    committed_modified: list[int] = []

    produced_created_total = 0
    produced_modified_total = 0
    committed_created_total = 0
    committed_modified_total = 0

    for day in days:
        created_produced, modified_produced, created_committed, modified_committed = daily.get(
            day.isoformat(), (0, 0, 0, 0)
        )

        produced_created_total += created_produced
        produced_modified_total += modified_produced
        committed_created_total += created_committed
        committed_modified_total += modified_committed

        produced_created.append(produced_created_total)
        produced_modified.append(produced_modified_total)
        committed_created.append(committed_created_total)
        committed_modified.append(committed_modified_total)

    figure = Figure(figsize=(12, 8))
    FigureCanvasAgg(figure)
    figure.patch.set_facecolor(BACKGROUND_COLOR)

    try:
        top_axes, bottom_axes = figure.subplots(2, 1, sharex=True)
        figure.subplots_adjust(hspace=0.18)

        pending_created = [
            max(produced - committed, 0) for produced, committed in zip(produced_created, committed_created)
        ]
        pending_modified = [
            max(produced - committed, 0) for produced, committed in zip(produced_modified, committed_modified)
        ]

        panel_series = (
            (
                top_axes,
                (
                    ("Committed (mod)", committed_modified, COMMITTED_MODIFIED_COLOR),
                    ("Pending (mod)", pending_modified, PENDING_MODIFIED_COLOR),
                ),
            ),
            (
                bottom_axes,
                (
                    ("Committed (new)", committed_created, COMMITTED_CREATED_COLOR),
                    ("Pending (new)", pending_created, PENDING_CREATED_COLOR),
                ),
            ),
        )

        smooth_dates = _smooth_dates(date_numbers)

        for axes, series in panel_series:
            axes.set_facecolor(AXES_COLOR)
            smooth_values = [_smooth_values(values) for _, values, _ in series]
            axes.stackplot(
                smooth_dates,
                *smooth_values,
                labels=[label for label, _, _ in series],
                colors=[color for _, _, color in series],
                baseline="zero",
                linewidth=0,
            )
            axes.margins(y=0.08)
            axes.yaxis.set_major_locator(MaxNLocator(integer=True))
            axes.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
            axes.tick_params(colors=TEXT_COLOR)

            for spine in axes.spines.values():
                spine.set_color(FRAME_COLOR)
                spine.set_linewidth(0.8)

            axes.legend(loc="upper left", frameon=False, labelcolor=TEXT_COLOR, ncol=2)

        top_axes.set_xlim(smooth_dates[0], smooth_dates[-1])

        date_locator = mdates.AutoDateLocator(minticks=3, maxticks=8)
        bottom_axes.xaxis.set_major_locator(date_locator)
        bottom_axes.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
        bottom_axes.xaxis.get_offset_text().set_visible(False)
        bottom_axes.yaxis.get_offset_text().set_color(TEXT_COLOR)
        top_axes.yaxis.get_offset_text().set_color(TEXT_COLOR)
        bottom_axes.text(
            0.99,
            0.01,
            footer_text,
            transform=bottom_axes.transAxes,
            ha="right",
            va="bottom",
            fontsize=9,
            color=BACKGROUND_COLOR,
            zorder=5,
        )

        temporary_path = settings.data_dir / ".chart.png.tmp"
        figure.savefig(
            temporary_path,
            format="png",
            dpi=160,
            bbox_inches="tight",
            facecolor=BACKGROUND_COLOR,
        )

        os.replace(temporary_path, settings.chart_path)
    finally:
        figure.clear()

    store.save_render_state(settings, max_rowid, event_count)


def render_conditionally(settings: store.Settings, force: bool = False) -> bool:
    max_rowid, _, day_count = store.get_event_totals(settings)
    render_state = store.get_render_state(settings)
    chart_exists = settings.chart_path.exists()
    now = int(time.time())

    if day_count < 2:
        # NOTE: chart needs at least two days of data
        return False

    should_render = (
        force
        or render_state is None
        or not chart_exists
        or render_state["render_version"] != store.RENDER_VERSION
        or (
            max_rowid != render_state["max_rowid"]
            and now - render_state["rendered_at"] >= settings.render_min_interval_seconds
        )
    )

    if should_render:
        render_chart(settings)

    return should_render


def run_render_loop(settings: store.Settings) -> None:
    while True:
        try:
            render_conditionally(settings)
        except Exception:
            logger.exception("render check failed")

        time.sleep(settings.render_check_seconds)


def main() -> None:
    settings = store.Settings.from_env()
    store.initialize_database(settings)
    render_conditionally(settings, force="--force" in sys.argv[1:])


if __name__ == "__main__":
    main()
