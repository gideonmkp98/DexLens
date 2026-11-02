// DexLens Privacy-Safe Product Analytics Client
// Adheres strictly to Workstream 3 specifications:
// - Zero raw images, zero OCR text, zero tokens or credentials
// - Non-blocking: analytics failures NEVER break scanning or user workflow
// - Bounded metadata only

import { ensureBrowserSession } from "@/lib/session";

export type ProductEventName =
  | "scan_started"
  | "camera_permission_granted"
  | "camera_permission_denied"
  | "capture_mode_changed"
  | "auto_capture_triggered"
  | "manual_capture_triggered"
  | "upload_started"
  | "upload_completed"
  | "scan_processing_started"
  | "scan_processing_completed"
  | "scan_processing_failed"
  | "no_card_detected"
  | "no_catalog_candidates"
  | "candidate_list_shown"
  | "candidate_selected"
  | "top_candidate_corrected"
  | "card_confirmed"
  | "card_added_to_collection"
  | "scan_abandoned"
  | "user_feedback_submitted";

export interface AnalyticsEventPayload {
  event_name: ProductEventName;
  schema_version?: number;
  session_id?: string | null;
  scan_id?: string | null;
  capture_mode?: "auto" | "manual" | "upload" | null;
  device_category?: "mobile" | "tablet" | "desktop" | null;
  browser_category?:
    | "safari_ios"
    | "chrome_android"
    | "chrome_desktop"
    | "firefox"
    | "safari_macos"
    | "other"
    | null;
  viewport_category?: "compact" | "standard" | "wide" | null;
  processing_duration_ms?: number | null;
  confidence_state?: "high" | "medium" | "low" | "none" | string | null;
  candidate_count?: number | null;
  is_top_suggestion_selected?: boolean | null;
  failure_category?: string | null;
  metadata?: Record<string, string | number | boolean | null>;
}

function detectDeviceCategory(): "mobile" | "tablet" | "desktop" {
  if (typeof window === "undefined") return "desktop";
  const w = window.innerWidth;
  if (w < 640) return "mobile";
  if (w <= 1024) return "tablet";
  return "desktop";
}

function detectViewportCategory(): "compact" | "standard" | "wide" {
  if (typeof window === "undefined") return "standard";
  const w = window.innerWidth;
  if (w < 640) return "compact";
  if (w <= 1024) return "standard";
  return "wide";
}

function detectBrowserCategory():
  | "safari_ios"
  | "chrome_android"
  | "chrome_desktop"
  | "firefox"
  | "safari_macos"
  | "other" {
  if (typeof navigator === "undefined") return "other";
  const ua = navigator.userAgent.toLowerCase();
  if (/iphone|ipad|ipod/.test(ua)) return "safari_ios";
  if (/android/.test(ua) && /chrome/.test(ua)) return "chrome_android";
  if (/chrome/.test(ua) && !/chromium|edg/.test(ua)) return "chrome_desktop";
  if (/firefox/.test(ua)) return "firefox";
  if (/safari/.test(ua) && /macintosh/.test(ua)) return "safari_macos";
  return "other";
}

/**
 * Fires a privacy-conscious product analytics event.
 * Absolutely guaranteed to be non-blocking and safe from throwing errors.
 */
export function trackEvent(
  eventName: ProductEventName,
  data: Partial<Omit<AnalyticsEventPayload, "event_name">> = {}
): void {
  try {
    if (typeof window === "undefined") return;

    const payload: AnalyticsEventPayload = {
      event_name: eventName,
      schema_version: 1,
      session_id: data.session_id ?? null,
      scan_id: data.scan_id ?? null,
      capture_mode: data.capture_mode ?? null,
      device_category: data.device_category ?? detectDeviceCategory(),
      browser_category: data.browser_category ?? detectBrowserCategory(),
      viewport_category: data.viewport_category ?? detectViewportCategory(),
      processing_duration_ms: data.processing_duration_ms ?? null,
      confidence_state: data.confidence_state ?? null,
      candidate_count: data.candidate_count ?? null,
      is_top_suggestion_selected: data.is_top_suggestion_selected ?? null,
      failure_category: data.failure_category ?? null,
      metadata: data.metadata ?? undefined,
    };

    void ensureBrowserSession()
      .then(() => {
        const url = "/api/v1/analytics/events";
        const body = JSON.stringify(payload);

        // Prefer sendBeacon for non-blocking unload safety.
        if (typeof navigator.sendBeacon === "function") {
          const blob = new Blob([body], { type: "application/json" });
          const queued = navigator.sendBeacon(url, blob);
          if (queued) return;
        }

        void fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
          keepalive: true,
          credentials: "include",
        }).catch(() => undefined);
      })
      .catch(() => undefined);
  } catch {
    // Non-fatal safety guard
  }
}
