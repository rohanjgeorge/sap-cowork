export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "include",
    ...init,
    headers: {
      ...(init.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: "Request failed" }));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Please check the submitted fields.",
    );
  }
  return response.json();
}
export const post = <T>(path: string, body: unknown = {}) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export async function streamChat(
  projectId: string,
  input: import("./types").ChatInput,
  onProgress: (status: string) => void,
): Promise<import("./types").ChatResult> {
  const response = await fetch(`/api/projects/${projectId}/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok || !response.body)
    throw new Error(
      response.status === 401
        ? "Session expired. Reload and sign in."
        : "Could not start the request. Retry when the backend is available.",
    );
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let buffer = "",
    result: import("./types").ChatResult | undefined;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const event = JSON.parse(line.slice(6));
      if (event.type === "progress") onProgress(event.task_status);
      if (event.type === "error") throw new Error(event.message);
      if (event.type === "result") result = event.data;
    }
    if (done) break;
  }
  if (!result)
    throw new Error(
      "Connection ended before confirmation. Refresh the project or retry the same request.",
    );
  return result;
}
