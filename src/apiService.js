import { formatProfileForApi } from "./profileBuilder.js";

export async function fetchJobMatches(userProfile, topK = 5) {
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filters: formatProfileForApi(userProfile.preferences),
      top_k: topK,
    }),
  });

  if (!response.ok) {
    throw new Error(`Job match request failed: ${response.status}`);
  }

  return response.json();
}
