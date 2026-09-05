"use client";

import { Calendar, ChevronLeft, ChevronRight, Upload } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiRequestError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  END_HOUR,
  HOUR_PX,
  START_HOUR,
  WEEK_DAY_COUNT,
  addDays,
  formatDayHeading,
  formatHourLabel,
  formatLongDay,
  formatWeekRange,
  gmtOffsetLabel,
  isAllDayEvent,
  isCancelledTitle,
  mondayOf,
  parseYmd,
  placeTimedEvents,
  ymdLocal,
} from "@/lib/calendarGrid";
import type { QcCalendarEvent } from "@/lib/types";

type ViewMode = "day" | "week";

function eventHref(event: QcCalendarEvent): React.ReactNode {
  const cancelled = isCancelledTitle(event.title);
  const className = `qc-cal-block-title${cancelled ? " is-cancelled" : ""}`;
  if (event.web_link?.startsWith("/")) {
    return (
      <Link className={className} href={event.web_link}>
        {event.title}
      </Link>
    );
  }
  if (event.web_link) {
    return (
      <a className={className} href={event.web_link} target="_blank" rel="noreferrer">
        {event.title}
      </a>
    );
  }
  return <div className={className}>{event.title}</div>;
}

export function QcCalendarView(): React.ReactElement {
  const { canUploadIcs } = useAuth();
  const [view, setView] = useState<ViewMode>("week");
  const [anchor, setAnchor] = useState(() => ymdLocal(new Date()));
  const [events, setEvents] = useState<QcCalendarEvent[]>([]);
  const [weekStart, setWeekStart] = useState(() => mondayOf(ymdLocal(new Date())));
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    const load = (): Promise<void> => {
      setLoading(true);
      setError(null);
      const request = view === "week" ? api.getCalendarWeek(anchor) : api.getCalendarDay(anchor);
      return request
        .then((data) => {
          if (cancelled) return;
          setEvents(data.events || []);
          setNote(data.outlook_note || null);
          if ("week_start" in data && data.week_start) {
            setWeekStart(data.week_start);
          } else {
            setWeekStart(mondayOf(anchor));
          }
        })
        .catch((err: unknown) => {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : "No se pudo cargar el calendario");
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };
    void load();
    const interval = window.setInterval(() => {
      void load();
    }, 5 * 60 * 1000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [view, anchor]);

  useEffect(() => {
    const node = scrollerRef.current;
    if (!node || loading) return;
    node.scrollTop = 0;
  }, [loading, view, anchor]);

  const handleIcs = async (file: File): Promise<void> => {
    setUploading(true);
    setError(null);
    try {
      await api.uploadCalendarIcs(file);
      const data = view === "week" ? await api.getCalendarWeek(anchor) : await api.getCalendarDay(anchor);
      setEvents(data.events || []);
      setNote(data.outlook_note || null);
      if ("week_start" in data && data.week_start) {
        setWeekStart(data.week_start);
      }
    } catch (err: unknown) {
      setError(err instanceof ApiRequestError ? err.message : err instanceof Error ? err.message : "No se pudo cargar el .ics");
    } finally {
      setUploading(false);
    }
  };

  const days = view === "week" ? Array.from({ length: WEEK_DAY_COUNT }, (_, index) => addDays(weekStart, index)) : [anchor];
  const hours = Array.from({ length: END_HOUR - START_HOUR }, (_, index) => START_HOUR + index);
  const today = ymdLocal(new Date());
  const rangeLabel = view === "week" ? formatWeekRange(weekStart) : formatLongDay(anchor);
  const now = new Date();
  const showNow = days.includes(today);
  const nowTop = ((now.getHours() - START_HOUR) * 60 + now.getMinutes()) / 60 * HOUR_PX;

  const step = view === "week" ? 7 : 1;
  const allDayByDay: Record<string, QcCalendarEvent[]> = {};
  for (const day of days) {
    allDayByDay[day] = events.filter((event) => isAllDayEvent(event) && ymdLocal(new Date(event.start)) === day);
  }

  return (
    <div className="panel qc-calendar">
      <div className="panel-header">
        <h2>
          <Calendar size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "6px" }} />
          Calendario QC
        </h2>
        <div className="qc-calendar-toggle">
          {canUploadIcs && (
            <button type="button" className="secondary" disabled={uploading} onClick={() => fileRef.current?.click()}>
              <Upload size={12} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: "4px" }} />
              {uploading ? "Cargando…" : "Cargar .ics"}
            </button>
          )}
          <button type="button" className={view === "day" ? "active" : ""} onClick={() => setView("day")}>
            Día
          </button>
          <button type="button" className={view === "week" ? "active" : ""} onClick={() => setView("week")}>
            Semana
          </button>
        </div>
      </div>
      <div className="panel-body qc-cal-body">
        {canUploadIcs && (
        <input
          ref={fileRef}
          type="file"
          accept=".ics,text/calendar"
          style={{ display: "none" }}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleIcs(file);
            event.target.value = "";
          }}
        />
        )}
        <div className="qc-cal-toolbar">
          <button type="button" className="secondary" onClick={() => setAnchor(ymdLocal(new Date()))}>
            Hoy
          </button>
          <button
            type="button"
            className="icon-close"
            aria-label={view === "week" ? "Semana anterior" : "Día anterior"}
            onClick={() => setAnchor((current) => addDays(current, -step))}
          >
            <ChevronLeft size={16} />
          </button>
          <button
            type="button"
            className="icon-close"
            aria-label={view === "week" ? "Semana siguiente" : "Día siguiente"}
            onClick={() => setAnchor((current) => addDays(current, step))}
          >
            <ChevronRight size={16} />
          </button>
          <span className="qc-cal-range">{rangeLabel}</span>
        </div>
        {note && !loading ? <p className="muted" style={{ marginTop: 0, fontSize: "12.5px", lineHeight: 1.45 }}>{note}</p> : null}
        {loading && <p className="muted">Cargando actividades…</p>}
        {error && <p className="error-text">{error}</p>}
        {!loading && !error && (
          <div className={`qc-cal-grid qc-cal-grid-${view}`}>
            <div className="qc-cal-head">
              <div className="qc-cal-gutter qc-cal-tz">{gmtOffsetLabel(parseYmd(anchor))}</div>
              {days.map((day) => (
                <button
                  key={day}
                  type="button"
                  className={`qc-cal-dayhead${day === today ? " is-today" : ""}`}
                  onClick={() => {
                    setAnchor(day);
                    setView("day");
                  }}
                >
                  {formatDayHeading(day)}
                </button>
              ))}
            </div>
            <div className="qc-cal-allday">
              <div className="qc-cal-gutter">Todo el día</div>
              {days.map((day) => (
                <div key={day} className="qc-cal-allday-cell">
                  {(allDayByDay[day] || []).map((event) => (
                    <div
                      key={`${event.id}-${event.start}`}
                      className={`qc-cal-allday-chip${isCancelledTitle(event.title) ? " is-cancelled" : ""}`}
                    >
                      {event.title}
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div className="qc-cal-scroll" ref={scrollerRef}>
              <div className="qc-cal-hours" style={{ height: hours.length * HOUR_PX }}>
                {hours.map((hour) => (
                  <div key={hour} className="qc-cal-hour" style={{ height: HOUR_PX }}>
                    <span>{formatHourLabel(hour)}</span>
                  </div>
                ))}
              </div>
              <div className="qc-cal-days" style={{ height: hours.length * HOUR_PX }}>
                {days.map((day) => {
                  const placed = placeTimedEvents(events, day);
                  return (
                    <div key={day} className={`qc-cal-col${day === today ? " is-today" : ""}`}>
                      {hours.map((hour) => (
                        <div key={hour} className="qc-cal-slot" style={{ height: HOUR_PX }} />
                      ))}
                      {placed.map((item) => (
                        <article
                          key={`${item.event.id}-${item.event.start}`}
                          className={`qc-cal-block${item.event.is_live ? " is-live" : ""}${item.cancelled ? " is-cancelled" : ""}`}
                          style={{
                            top: item.top,
                            height: item.height,
                            left: `calc(${(item.col / item.colCount) * 100}% + 2px)`,
                            width: `calc(${100 / item.colCount}% - 4px)`,
                          }}
                          title={item.event.title}
                        >
                          {eventHref(item.event)}
                          {item.event.location ? (
                            <div className="qc-cal-block-sub">{item.event.location}</div>
                          ) : null}
                        </article>
                      ))}
                      {showNow && day === today && nowTop >= 0 && nowTop <= hours.length * HOUR_PX ? (
                        <div className="qc-cal-now" style={{ top: nowTop }} />
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
