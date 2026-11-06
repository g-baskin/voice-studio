export class ApiError extends Error {}

/** Fetches an app API path and turns a non-2xx response into a readable ApiError. */
export async function request(url: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = 'The request failed.';
    try {
      const body: unknown = await response.json();
      if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') detail = body.detail;
    } catch {
      // Non-JSON error bodies keep the generic message.
    }
    throw new ApiError(detail);
  }
  return response;
}
