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
      const b2Url = new URL(`https://${env.B2_BUCKET}.${env.B2_ENDPOINT}/${fileName}`);
      
      // Explicitly sign the Content-Type header that the browser will send
      const signed = await aws.sign(new Request(b2Url, { 
          method: 'PUT',
          headers: { 'Content-Type': 'video/mp4' }
      }), { aws: { signQuery: true } });
      
      return new Response(JSON.stringify({ uploadUrl: signed.url, fileName }), { headers: cors });
    }

// 2. TRIGGER GITHUB RUNNERS
    if (url.pathname === "/start" && request.method === "POST") {
      const { fileName } = await request.json();
      const jobId = "job_" + Math.random().toString(36).substr(2, 9);
      
      const b2Url = new URL(`https://${env.B2_BUCKET}.${env.B2_ENDPOINT}/${fileName}`);
      const signedGet = await aws.sign(new Request(b2Url, { method: 'GET' }), { aws: { signQuery: true } });
      
      // Store the fileName in its own isolated key for the auto-delete later
      await fetch(`${env.UPSTASH_URL}/set/file_${jobId}/${fileName}`, {
        headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` }
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
      
      // Fetch the isolated atomic keys
      const compRes = await fetch(`${env.UPSTASH_URL}/get/comp_${jobId}`, { headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` } });
      const tsRes = await fetch(`${env.UPSTASH_URL}/smembers/ts_${jobId}`, { headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` } });
      
      const compData = await compRes.json();
      const tsData = await tsRes.json();
      
      const completed = parseInt(compData.result || 0);
      const timestamps = tsData.result ? tsData.result.map(Number) : [];
      const status = completed >= 160 ? "completed" : "processing";
      
      // We return it exactly as the frontend expects it, so no frontend changes are needed
      return new Response(JSON.stringify({ status, completed, timestamps }), { headers: cors });
    }

    // 4. RECEIVE AI LOGS & AUTO-DELETE VIDEO
    if (url.pathname === "/update" && request.method === "POST") {
      const { jobId, foundTimestamps } = await request.json();
      
      // ATOMIC INCR: Forces Redis to perfectly add +1 in a queue, impossible to overwrite
      const incRes = await fetch(`${env.UPSTASH_URL}/incr/comp_${jobId}`, {
        headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` }
      });
      const completedCount = (await incRes.json()).result;

      // ATOMIC SADD: Safely adds timestamps to a Redis Set
      if (foundTimestamps && foundTimestamps.length > 0) {
        for (const ts of foundTimestamps) {
           await fetch(`${env.UPSTASH_URL}/sadd/ts_${jobId}/${ts}`, {
             headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` }
           });
        }
      }
      
      if (completedCount >= 160) {
        const fileRes = await fetch(`${env.UPSTASH_URL}/get/file_${jobId}`, {
           headers: { Authorization: `Bearer ${env.UPSTASH_TOKEN}` }
        });
        const fileName = (await fileRes.json()).result;
        
        if (fileName) {
            const deleteUrl = new URL(`https://${env.B2_BUCKET}.${env.B2_ENDPOINT}/${fileName}`);
            const deleteReq = await aws.sign(new Request(deleteUrl, { method: 'DELETE' }));
            await fetch(deleteReq);
        }
      }

      return new Response("Updated", { status: 200, headers: cors });
    }

    return new Response("Not Found", { status: 404, headers: cors });
  }
};