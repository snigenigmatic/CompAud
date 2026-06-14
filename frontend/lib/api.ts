import {
  getHealth,
  getPs3Requirements,
  type HealthResponse,
  type HttpValidationError,
  type Ps3ReportResponse,
  type RequirementCatalogResponse,
} from "@/api-client";

export type {
  AgentTraceEntry,
  HealthResponse,
  Ps3LinkedEvidenceView,
  Ps3ReportResponse,
  Ps3Summary,
  Requirement,
  RequirementCatalogResponse,
  RequirementReport,
} from "@/api-client";

export type ErrorResponse = {
  error: {
    code: string;
    message: string;
  };
};


export type AnalysisStreamStep = {
  id: string;
  label: string;
};

export type AnalysisProgressEvent = {
  request_id: string;
  step: string;
  label: string;
  status: string;
  progress: number;
  message: string;
};

export type AnalysisStartedEvent = {
  request_id: string;
  uploaded_filename: string;
  steps: AnalysisStreamStep[];
};

export type Ps3StreamHandlers = {
  onStarted?: (event: AnalysisStartedEvent) => void;
  onProgress?: (event: AnalysisProgressEvent) => void;
  onComplete?: (response: Ps3ReportResponse) => void;
  onError?: (error: ApiRequestError) => void;
};

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiRequestError extends Error {
  code: string;

  constructor(message: string, code = "API_ERROR") {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
  }
}

function isErrorResponse(error: unknown): error is ErrorResponse {
  return (
    typeof error === "object" &&
    error !== null &&
    "error" in error &&
    typeof (error as ErrorResponse).error?.message === "string"
  );
}

function isValidationError(error: unknown): error is HttpValidationError {
  return (
    typeof error === "object" &&
    error !== null &&
    "detail" in error &&
    Array.isArray((error as HttpValidationError).detail)
  );
}

export function toApiRequestError(error: unknown): ApiRequestError {
  if (isErrorResponse(error)) {
    return new ApiRequestError(error.error.message, error.error.code);
  }

  if (isValidationError(error)) {
    const message =
      error.detail?.map((detail) => detail.msg).join("; ") ||
      "The backend rejected the request.";
    return new ApiRequestError(message, "VALIDATION_ERROR");
  }

  if (error instanceof Error) {
    return new ApiRequestError(error.message, "NETWORK_ERROR");
  }

  return new ApiRequestError("The backend request failed.");
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function asString(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function normalizeStartedEvent(value: unknown): AnalysisStartedEvent {
  const record = asRecord(value);
  const steps = asRecordArray(record.steps).map((step) => ({
    id: asString(step.id),
    label: asString(step.label),
  }));

  return {
    request_id: asString(record.request_id),
    uploaded_filename: asString(record.uploaded_filename),
    steps,
  };
}

function normalizeProgressEvent(value: unknown): AnalysisProgressEvent {
  const record = asRecord(value);

  return {
    request_id: asString(record.request_id),
    step: asString(record.step),
    label: asString(record.label),
    status: asString(record.status),
    progress: asNumber(record.progress),
    message: asString(record.message),
  };
}

function ps3ResponseFromEvent(value: unknown): Ps3ReportResponse {
  const record = asRecord(value);
  const response = record.response;
  if (typeof response !== "object" || response === null) {
    throw new ApiRequestError("PS3 analysis completed without a response.");
  }
  return response as Ps3ReportResponse;
}

function errorFromEvent(value: unknown): ApiRequestError {
  const record = asRecord(value);
  return new ApiRequestError(
    asString(record.message) || "Analysis stream failed.",
    asString(record.code) || "ANALYSIS_STREAM_ERROR",
  );
}

function parseSseBlock(block: string): { event: string; data: unknown } | null {
  const eventLine = block.split("\n").find((line) => line.startsWith("event:"));
  const dataLines = block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart());

  if (!dataLines.length) return null;

  return {
    event: eventLine?.slice(6).trim() || "message",
    data: JSON.parse(dataLines.join("\n")) as unknown,
  };
}

async function readPs3Stream(
  response: Response,
  handlers: Ps3StreamHandlers = {},
): Promise<Ps3ReportResponse> {
  if (!response.ok || !response.body) {
    throw new ApiRequestError(
      await response.text().catch(() => "PS3 analysis stream failed."),
      `HTTP_${response.status}`,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: Ps3ReportResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const parsed = parseSseBlock(block.trim());
      if (!parsed) continue;

      if (parsed.event === "analysis.started") {
        handlers.onStarted?.(normalizeStartedEvent(parsed.data));
      } else if (parsed.event === "analysis.progress") {
        handlers.onProgress?.(normalizeProgressEvent(parsed.data));
      } else if (parsed.event === "analysis.complete") {
        finalResponse = ps3ResponseFromEvent(parsed.data);
        handlers.onComplete?.(finalResponse);
      } else if (parsed.event === "analysis.error") {
        const streamError = errorFromEvent(parsed.data);
        handlers.onError?.(streamError);
        throw streamError;
      }
    }
    if (done) break;
  }

  if (!finalResponse) {
    throw new ApiRequestError("PS3 analysis stream ended before completion.");
  }
  return finalResponse;
}

export async function fetchBackendHealth(): Promise<HealthResponse> {
  try {
    const response = await getHealth({
      baseUrl: apiBaseUrl,
      throwOnError: true,
    });
    return response.data;
  } catch (error) {
    throw toApiRequestError(error);
  }
}

export async function streamPs3Analysis(
  handlers: Ps3StreamHandlers = {},
): Promise<Ps3ReportResponse> {
  try {
    const response = await fetch(`${apiBaseUrl}/ps3/analyze/stream`, {
      headers: { Accept: "text/event-stream" },
    });
    return await readPs3Stream(response, handlers);
  } catch (error) {
    throw toApiRequestError(error);
  }
}

export async function fetchPs3Requirements(): Promise<RequirementCatalogResponse> {
  try {
    const response = await getPs3Requirements({
      baseUrl: apiBaseUrl,
      throwOnError: true,
    });
    return response.data;
  } catch (error) {
    throw toApiRequestError(error);
  }
}

export function ps3ReportPdfUrl(): string {
  return `${apiBaseUrl}/ps3/report.pdf`;
}
