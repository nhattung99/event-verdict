# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json
from dataclasses import dataclass

@allow_storage
@dataclass
class EventQuery:
    creator: Address
    event_description: str
    resolution_deadline: str
    category: str
    source_urls: DynArray[str]
    status: str
    resolution: str
    confidence: bigint
    reasoning: str
    evidence_summary: str
    sources_readable: bigint


class Contract(gl.Contract):
    queries: TreeMap[str, EventQuery]
    next_id: bigint
    owner: Address

    def __init__(self):
        self.owner = gl.message.sender_address
        self.next_id = bigint(1)

    @gl.public.write
    def create_query(self, event_description: str, resolution_deadline: str,
                     category: str, source_urls: DynArray[str]) -> str:
        if not event_description.strip():
            raise gl.vm.UserError("event_description cannot be empty")
        if len(event_description) > 500:
            raise gl.vm.UserError("event_description exceeds 500 characters")
        if not resolution_deadline.strip():
            raise gl.vm.UserError("resolution_deadline cannot be empty")
        if len(resolution_deadline) > 50:
            raise gl.vm.UserError("resolution_deadline exceeds 50 characters")
        if category not in ["FINANCE", "POLITICS", "SPORTS", "TECH", "SCIENCE", "CRYPTO", "OTHER"]:
            raise gl.vm.UserError("Invalid category")
        if len(source_urls) < 3:
            raise gl.vm.UserError("At least 3 source URLs required")
        if len(source_urls) > 5:
            raise gl.vm.UserError("Maximum 5 source URLs")
        seen = []
        for url in source_urls:
            if not (url.startswith("http://") or url.startswith("https://")):
                raise gl.vm.UserError("Invalid URL")
            if url in seen:
                raise gl.vm.UserError("Duplicate source URL")
            seen.append(url)
        query_id = str(self.next_id)
        self.queries[query_id] = EventQuery(
            gl.message.sender_address, event_description, resolution_deadline,
            category, source_urls, "PENDING", "", bigint(0), "", "[]", bigint(0))
        self.next_id += bigint(1)
        return query_id

    @gl.public.write
    def resolve_query(self, query_id: str) -> None:
        if query_id not in self.queries:
            raise gl.vm.UserError("Query not found")
        query = self.queries[query_id]
        if query.status != "PENDING":
            raise gl.vm.UserError("Query is not PENDING")
        source_urls_list = list(query.source_urls)
        event_desc_cap = query.event_description
        deadline_cap = query.resolution_deadline
        category_cap = query.category

        def leader_fn():
            # 1. Fetch each source URL; catch failures individually
            source_results = []
            readable_count = 0
            for url in source_urls_list:
                try:
                    res = gl.nondet.web.render(url)
                    body = res.body if hasattr(res, 'body') else str(res)
                    if body and len(body.strip()) > 30:
                        source_results.append(
                            f"Source [{url}]:\n{body[:3000]}"
                        )
                        readable_count += 1
                    else:
                        source_results.append(
                            f"Source [{url}]: (empty or too short)"
                        )
                except Exception as e:
                    source_results.append(
                        f"Source [{url}]: (fetch failed: {str(e)})"
                    )

            # 2. Build prompt
            prompt = f"""You are an expert event resolution oracle on GenLayer.
        Your job is to determine whether a specific real-world event occurred,
        based solely on the public evidence sources provided.

        Event to Resolve: "{event_desc_cap}"
        Resolution Deadline: {deadline_cap}
        Category: {category_cap}

        Public evidence sources fetched on-chain:
        {chr(10).join(source_results)}

        Resolution instructions:
        1. Read each source carefully for evidence about the event.
        2. Determine whether the event has clearly occurred based on the
           evidence in the readable sources.
        3. Do NOT assume or infer from general knowledge ? base your resolution
           ONLY on what the fetched sources explicitly state.
        4. If sources contradict each other, note the contradiction in reasoning
           and return INCONCLUSIVE.

        Resolution options:
        - "YES": The event clearly occurred. At least 2 readable sources
          explicitly confirm it. Be specific about what evidence confirms it.
        - "NO": The event clearly did NOT occur, and the resolution deadline
          has passed. At least 1 readable source confirms the non-occurrence
          or the deadline has passed without the event happening.
        - "TOO_EARLY": The resolution deadline has not yet passed based on
          the date context in the sources, and the event has not occurred yet.
          This is not a final resolution ? the query can be re-evaluated later.
        - "INCONCLUSIVE": Fewer than 2 sources returned readable content, OR
          sources explicitly contradict each other, OR the evidence is
          ambiguous and cannot be resolved without more information.

        CRITICAL RULES:
        - You MUST base YES or NO on explicit evidence from the sources.
          Do not resolve YES or NO if you cannot cite specific evidence.
        - If fewer than 2 sources returned readable content, return INCONCLUSIVE.
        - TOO_EARLY is NOT a final resolution ? use it only when the deadline
          is clearly in the future.

        For evidence_summary: one object per source URL (include unreadable ones).

        Return ONLY raw JSON, no markdown, no backticks:
        {{"resolution": "YES"|"NO"|"TOO_EARLY"|"INCONCLUSIVE",
          "confidence": <0-100>,
          "reasoning": "<2-3 sentences citing specific evidence from sources>",
          "sources_readable": <integer>,
          "evidence_summary": [
            {{"url": "<source url>",
              "readable": true|false,
              "relevant": true|false,
              "key_finding": "<what this source says about the event or why unreadable>"
            }}
          ]}}"""


            # 3. Parse with safe fallback; return a safe result on failure
            try:
                raw = gl.nondet.exec_prompt(prompt, response_format="json")
                if isinstance(raw, dict):
                    parsed = raw
                else:
                    cleaned = str(raw).strip()
                    if cleaned.startswith("```json"): cleaned = cleaned[7:]
                    if cleaned.startswith("```"): cleaned = cleaned[3:]
                    if cleaned.endswith("```"): cleaned = cleaned[:-3]
                    parsed = json.loads(cleaned.strip())

                resolution = parsed.get("resolution", "INCONCLUSIVE")
                if resolution not in ["YES", "NO", "TOO_EARLY", "INCONCLUSIVE"]:
                    resolution = "INCONCLUSIVE"

                try: conf = max(0, min(100, int(parsed.get("confidence", 0))))
                except: conf = 0

                src_read = readable_count

                # Critical consistency rules:
                # Rule 1: YES or NO requires at least 2 readable sources
                if resolution in ["YES", "NO"] and src_read < 2:
                    resolution = "INCONCLUSIVE"
                    conf = max(0, conf - 20)

                # Rule 2: TOO_EARLY should have lower confidence cap
                if resolution == "TOO_EARLY" and conf > 80:
                    conf = 80

                # Rule 3: INCONCLUSIVE should reflect uncertainty
                if resolution == "INCONCLUSIVE" and conf > 50:
                    conf = 50

                # Validate evidence_summary
                raw_summary = parsed.get("evidence_summary", [])
                if not isinstance(raw_summary, list): raw_summary = []
                clean_summary = []
                for s in raw_summary:
                    if isinstance(s, dict):
                        clean_summary.append({
                            "url": str(s.get("url", "")),
                            "readable": bool(s.get("readable", False)),
                            "relevant": bool(s.get("relevant", False)),
                            "key_finding": str(s.get("key_finding", ""))
                        })

                return {
                    "resolution": resolution,
                    "confidence": conf,
                    "reasoning": str(parsed.get("reasoning", "")),
                    "sources_readable": src_read,
                    "evidence_summary": json.dumps(clean_summary)
                }
            except Exception as e:
                return {
                    "resolution": "INCONCLUSIVE",
                    "confidence": 0,
                    "reasoning": f"Parse error: {str(e)}",
                    "sources_readable": readable_count,
                    "evidence_summary": "[]"
                }


        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            lp = leader_res.calldata
            if not isinstance(lp, dict):
                return False

            leader_resolution = lp.get("resolution")
            leader_conf = lp.get("confidence")
            leader_src = lp.get("sources_readable", 0)

            if leader_resolution not in ["YES", "NO", "TOO_EARLY", "INCONCLUSIVE"]:
                return False
            try:
                lc = int(leader_conf)
                if not (0 <= lc <= 100): return False
            except:
                return False

            try:
                my_result = leader_fn()
            except:
                return False

            # Resolution must match exactly: this is the oracle output
            if my_result.get("resolution") != leader_resolution:
                return False

            # For YES or NO: both validators must have at least 1 readable source
            # Cannot confirm event happened/didnt without reading any source
            if leader_resolution in ["YES", "NO"]:
                try:
                    my_src = int(my_result.get("sources_readable", 0))
                    l_src = int(leader_src)
                    if my_src < 1 or l_src < 1:
                        return False
                except:
                    return False

            # Confidence banding: 0-34, 35-79, 80-100
            try:
                mc = int(my_result.get("confidence", 0))
                if not (0 <= mc <= 100): return False
            except:
                return False

            def _band(c):
                if c < 35: return 1
                elif c < 80: return 2
                else: return 3

            return _band(mc) == _band(lc)


        # Execute and unpack result
        ruling = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        result_data = ruling.calldata if hasattr(ruling, 'calldata') else ruling

        result_resolution = result_data.get("resolution", "INCONCLUSIVE")
        query.resolution = result_resolution
        query.confidence = bigint(result_data.get("confidence", 0))
        query.reasoning = str(result_data.get("reasoning", ""))
        query.sources_readable = bigint(result_data.get("sources_readable", 0))
        query.evidence_summary = str(result_data.get("evidence_summary", "[]"))

        # Status update logic:
        # YES/NO -> RESOLVED (final)
        # INCONCLUSIVE -> UNRESOLVABLE (final)
        # TOO_EARLY -> keep PENDING (can retry later)
        if result_resolution in ["YES", "NO"]:
            query.status = "RESOLVED"
        elif result_resolution == "INCONCLUSIVE":
            query.status = "UNRESOLVABLE"
        # TOO_EARLY: status stays "PENDING"; no change needed

        self.queries[query_id] = query
    @gl.public.write
    def invalidate_query(self, query_id: str) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("Only owner")
        if query_id not in self.queries:
            raise gl.vm.UserError("Query not found")
        q = self.queries[query_id]
        if q.status != "PENDING":
            raise gl.vm.UserError("Query is not PENDING")
        q.status = "UNRESOLVABLE"
        q.reasoning = "Invalidated by admin"
        self.queries[query_id] = q

    @gl.public.view
    def get_query(self, query_id: str) -> str:
        if query_id not in self.queries:
            raise gl.vm.UserError("Query not found")
        q = self.queries[query_id]
        return json.dumps({"query_id": query_id, "creator": str(q.creator),
            "event_description": q.event_description,
            "resolution_deadline": q.resolution_deadline,
            "category": q.category, "source_urls": list(q.source_urls),
            "status": q.status, "resolution": q.resolution,
            "confidence": int(q.confidence), "reasoning": q.reasoning,
            "evidence_summary": q.evidence_summary,
            "sources_readable": int(q.sources_readable)})

    @gl.public.view
    def get_resolution(self, query_id: str) -> str:
        data = json.loads(self.get_query(query_id))
        if data["status"] == "PENDING" and data["resolution"] == "":
            raise gl.vm.UserError("Not yet resolved")
        del data["creator"]
        del data["source_urls"]
        return json.dumps(data)

    @gl.public.view
    def list_queries(self, resolution_filter: str) -> str:
        if resolution_filter not in ["", "PENDING", "YES", "NO", "TOO_EARLY", "INCONCLUSIVE", "UNRESOLVABLE"]:
            raise gl.vm.UserError("Invalid resolution filter")
        results = []
        for number in range(1, int(self.next_id)):
            query_id = str(number)
            q = self.queries[query_id]
            if resolution_filter in ["PENDING", "UNRESOLVABLE"]:
                if q.status != resolution_filter:
                    continue
            elif resolution_filter and q.resolution != resolution_filter:
                continue
            results.append({"query_id": query_id,
                "event_description": q.event_description, "category": q.category,
                "resolution_deadline": q.resolution_deadline,
                "status": q.status, "resolution": q.resolution,
                "confidence": int(q.confidence)})
        return json.dumps({"queries": results})

    @gl.public.view
    def get_count(self) -> int:
        return int(self.next_id) - 1
