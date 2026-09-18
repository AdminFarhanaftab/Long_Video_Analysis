export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // CORS Headers for Frontend
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });

    // 1. START JOB: Frontend sends video URL here
    if (url.pathname === "/start" && request.method === "POST") {
      const { videoUrl } = await request.json();
      const jobId = "job_" + Math.random().toString(36).substr(2, 9);
      
      // Initialize job in Upstash Redis (0 out of 160 chunks done)
      await fetch(`${env.UPSTASH_URL}/set/${jobId}`, {
        headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` },
        method: "POST",
        body: JSON.stringify({ status: "processing", completed: 0, timestamps: [] })
      });

      // Trigger GitHub Action
      await fetch(`https://api.github.com/repos/YOUR_USERNAME/YOUR_REPO/dispatches`, {
        method: "POST",
        headers: {
          "Accept": "application/vnd.github.v3+json",
          "Authorization": `token ${env.GH_PAT}`,
          "User-Agent": "Cloudflare-Worker"
        },
        body: JSON.stringify({
          event_type: "process_video",
          client_payload: { video_url: videoUrl, job_id: jobId }
        })
      });

      return new Response(JSON.stringify({ jobId }), { headers: cors });
    }

    // 2. CHECK STATUS: Frontend polls this endpoint
    if (url.pathname.startsWith("/status/")) {
      const jobId = url.pathname.split("/")[2];
      const redisRes = await fetch(`${env.UPSTASH_URL}/get/${jobId}`, {
        headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` }
      });
      const { result } = await redisRes.json();
      return new Response(result, { headers: cors });
    }

    // 3. UPDATE JOB: GitHub Runners post their results here
    if (url.pathname === "/update" && request.method === "POST") {
      const { jobId, chunkId, foundTimestamps } = await request.json();
      
      // Get current state
      const stateRes = await fetch(`${env.UPSTASH_URL}/get/${jobId}`, {
        headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` }
      });
      let state = JSON.parse((await stateRes.json()).result);
      
      // Update state
      state.completed += 1;
      state.timestamps.push(...foundTimestamps);
      if (state.completed >= 160) state.status = "completed";

      // Save back to Redis
      await fetch(`${env.UPSTASH_URL}/set/${jobId}`, {
        headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` },
        method: "POST",
        body: JSON.stringify(state)
      });
      return new Response("Updated", { status: 200 });
    }

    return new Response("Not Found", { status: 404 });
  }
};