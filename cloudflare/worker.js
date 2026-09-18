import { AwsClient } from 'aws4fetch';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, GET, OPTIONS, PUT, DELETE",
      "Access-Control-Allow-Headers": "Content-Type, Authorization"
    };

    if (request.method === "OPTIONS") return new Response(null, { headers: cors });

    // SECURITY: Validate Master Password
    const authHeader = request.headers.get("Authorization");
    if (authHeader !== `Bearer ${env.API_SECRET}`) {
      return new Response(JSON.stringify({ error: "Unauthorized access" }), { status: 401, headers: cors });
    }

    const aws = new AwsClient({
      accessKeyId: env.B2_KEY_ID,
      secretAccessKey: env.B2_APPLICATION_KEY,
      service: 's3',
      region: env.B2_REGION,
    });

    // 1. GENERATE DIRECT CLOUD UPLOAD LINK
    if (url.pathname === "/get-upload-link" && request.method === "GET") {
      const fileName = `vid_${Date.now()}.mp4`;
      const b2Url = new URL(`https://${env.B2_ENDPOINT}/${env.B2_BUCKET}/${fileName}`);
      
      const signed = await aws.sign(new Request(b2Url, { method: 'PUT' }), { aws: { signQuery: true } });
      return new Response(JSON.stringify({ uploadUrl: signed.url, fileName }), { headers: cors });
    }

    // 2. TRIGGER GITHUB RUNNERS
    if (url.pathname === "/start" && request.method === "POST") {
      const { fileName } = await request.json();
      const jobId = "job_" + Math.random().toString(36).substr(2, 9);
      
      // Generate a secure read link specifically for GitHub runners
      const b2Url = new URL(`https://${env.B2_ENDPOINT}/${env.B2_BUCKET}/${fileName}`);
      const signedGet = await aws.sign(new Request(b2Url, { method: 'GET' }), { aws: { signQuery: true } });
      
      await fetch(`${env.UPSTASH_URL}/set/${jobId}`, {
        headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` },
        method: "POST",
        body: JSON.stringify({ status: "processing", completed: 0, timestamps: [], fileName: fileName })
      });

      await fetch(`https://api.github.com/repos/${env.GITHUB_USERNAME}/${env.GITHUB_REPO}/dispatches`, {
        method: "POST",
        headers: {
          "Accept": "application/vnd.github.v3+json",
          "Authorization": `token ${env.GH_PAT}`,
          "User-Agent": "CF-Worker"
        },
        body: JSON.stringify({
          event_type: "process_video",
          client_payload: { video_url: signedGet.url, job_id: jobId }
        })
      });

      return new Response(JSON.stringify({ jobId }), { headers: cors });
    }

    // 3. FRONTEND POLLING STATUS
    if (url.pathname.startsWith("/status/")) {
      const jobId = url.pathname.split("/")[2];
      const redisRes = await fetch(`${env.UPSTASH_URL}/get/${jobId}`, {
        headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` }
      });
      const { result } = await redisRes.json();
      return new Response(result, { headers: cors });
    }

    // 4. RECEIVE AI LOGS & AUTO-DELETE VIDEO
    if (url.pathname === "/update" && request.method === "POST") {
      const { jobId, foundTimestamps } = await request.json();
      
      const stateRes = await fetch(`${env.UPSTASH_URL}/get/${jobId}`, {
        headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` }
      });
      let state = JSON.parse((await stateRes.json()).result);
      
      state.completed += 1;
      state.timestamps.push(...foundTimestamps);
      
      // Purge the video from Backblaze once all 160 runners finish
      if (state.completed >= 160) {
        state.status = "completed";
        const deleteUrl = new URL(`https://${env.B2_ENDPOINT}/${env.B2_BUCKET}/${state.fileName}`);
        const deleteReq = await aws.sign(new Request(deleteUrl, { method: 'DELETE' }));
        await fetch(deleteReq);
      }

      await fetch(`${env.UPSTASH_URL}/set/${jobId}`, {
        headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` },
        method: "POST",
        body: JSON.stringify(state)
      });
      
      return new Response("Updated", { status: 200, headers: cors });
    }

    return new Response("Not Found", { status: 404, headers: cors });
  }
};