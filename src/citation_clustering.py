import warnings
import re
from collections import defaultdict, deque, Counter
from typing import List, Dict, Any
from src.models import CitationResult
import os

# --- Clustering and propagation logic moved from unified_citation_processor_v2.py ---

def group_citations_into_clusters(citations: list, original_text: str = None) -> list:
    clusters_by_id = {}
    # --- NEW: If any member of a parallel group is verified, cluster all members together ---
    # Build a mapping from citation to its parallel group
    citation_to_group = {}
    for citation in citations:
        if getattr(citation, 'parallel_citations', None):
            group = set([citation.citation] + list(citation.parallel_citations))
            for c in group:
                citation_to_group[c] = group
    # Find all unique groups
    seen_groups = set()
    for group in citation_to_group.values():
        group_key = tuple(sorted(group))
        if group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        group_members = [c for c in citations if c.citation in group]
        if len(group_members) > 1:
            any_verified = any(getattr(c, 'verified', False) for c in group_members)
            if any_verified:
                # Cluster all members together
                cluster_id = f"fallback_parallel_{'_'.join(sorted(group))}"
                for c in group_members:
                    if not hasattr(c, 'metadata') or c.metadata is None:
                        c.metadata = {}
                    c.metadata['is_in_cluster'] = True
                    c.metadata['cluster_id'] = cluster_id
                # Add to clusters_by_id if not already present
                if cluster_id not in clusters_by_id:
                    clusters_by_id[cluster_id] = []
                for c in group_members:
                    if c not in clusters_by_id[cluster_id]:
                        clusters_by_id[cluster_id].append(c)
    # --- NEW LOGIC: Group by canonical name/date if not already clustered ---
    # Build a mapping from (canonical_name, canonical_date) to citations
    canonical_clusters = {}
    for citation in citations:
        canonical_name = getattr(citation, 'canonical_name', None)
        canonical_date = getattr(citation, 'canonical_date', None)
        verified = getattr(citation, 'verified', False)
        # Only cluster if canonical_name and canonical_date are present
        if canonical_name and canonical_date:
            key = (canonical_name, canonical_date)
            if key not in canonical_clusters:
                canonical_clusters[key] = []
            canonical_clusters[key].append(citation)
    # Add canonical clusters to clusters_by_id if not already present
    for key, members in canonical_clusters.items():
        # Only add if more than one member and not already clustered
        if len(members) > 1:
            # Generate a synthetic cluster_id
            cluster_id = f"canonical_{key[0]}_{key[1]}"
            if cluster_id not in clusters_by_id:
                clusters_by_id[cluster_id] = []
            # Only add citations not already in any cluster
            for citation in members:
                already_clustered = False
                if hasattr(citation, 'metadata') and citation.metadata:
                    already_clustered = citation.metadata.get('is_in_cluster', False)
                elif isinstance(citation, dict):
                    already_clustered = citation.get('metadata', {}).get('is_in_cluster', False)
                if not already_clustered:
                    clusters_by_id[cluster_id].append(citation)
                    # Mark as in cluster
                    if hasattr(citation, 'metadata'):
                        citation.metadata = citation.metadata or {}
                        citation.metadata['is_in_cluster'] = True
                        citation.metadata['cluster_id'] = cluster_id
                    elif isinstance(citation, dict):
                        citation.setdefault('metadata', {})
                        citation['metadata']['is_in_cluster'] = True
                        citation['metadata']['cluster_id'] = cluster_id
            # Conservative propagation: only fill missing extracted_case_name
            best_extracted = None
            for c in members:
                if getattr(c, 'extracted_case_name', None):
                    best_extracted = c.extracted_case_name
                    break
            if best_extracted:
                for c in members:
                    if not getattr(c, 'extracted_case_name', None):
                        c.extracted_case_name = best_extracted
    # --- IMPROVED PROPAGATION: Propagate normalized extracted case name and year to all citations in a group ---
    def normalize_case_name(name):
        if not name:
            return None
        import re
        # Remove everything after the first comma followed by a number (e.g., ', 200 Wn.2d 72')
        name = re.split(r',\s*\d', name)[0]
        # Remove everything after the first parenthesis
        name = re.split(r'\(', name)[0]
        return name.strip()
    # Build a mapping from (extracted_date) to all extracted names in that group
    date_to_names = {}
    for c in citations:
        date = getattr(c, 'extracted_date', None)
        name = getattr(c, 'extracted_case_name', None)
        if date and name:
            norm_name = normalize_case_name(name)
            if norm_name:
                date_to_names.setdefault(date, []).append(norm_name)
    # For each date, pick the most common normalized name
    date_to_best_name = {}
    for date, names in date_to_names.items():
        from collections import Counter
        best_name, _ = Counter(names).most_common(1)[0]
        date_to_best_name[date] = best_name
    # Propagate the best name to all citations with that date
    for c in citations:
        date = getattr(c, 'extracted_date', None)
        if date and date in date_to_best_name:
            setattr(c, 'extracted_case_name', date_to_best_name[date])
    # Try to infer missing extracted case names from canonical name or previous citation with same date
    for i, c in enumerate(citations):
        if not getattr(c, 'extracted_case_name', None) and getattr(c, 'extracted_date', None):
            # Try canonical name
            if getattr(c, 'canonical_name', None):
                c.extracted_case_name = c.canonical_name
            else:
                # Try previous citation with same date
                for prev in reversed(citations[:i]):
                    if getattr(prev, 'extracted_date', None) == c.extracted_date and getattr(prev, 'extracted_case_name', None):
                        c.extracted_case_name = prev.extracted_case_name
                        break
    # --- NEW: Propagate canonical name to adjacent citations with same date if one has it ---
    for i, c in enumerate(citations):
        if not getattr(c, 'extracted_case_name', None) and getattr(c, 'extracted_date', None):
            for j, other in enumerate(citations):
                if i == j:
                    continue
                if getattr(other, 'extracted_date', None) == getattr(c, 'extracted_date', None) and getattr(other, 'canonical_name', None):
                    # Check adjacency (within 100 characters)
                    if hasattr(c, 'start_index') and hasattr(other, 'end_index') and c.start_index is not None and other.end_index is not None:
                        if 0 <= c.start_index - other.end_index <= 100:
                            c.extracted_case_name = other.canonical_name
                            break
    # --- NEW: Group sequences matching [case name], [citation], [page], [citation], ..., ([year]) ---
    import re
    STOPWORDS = {"of", "and", "the", "in", "for", "on", "at", "by", "with", "to", "from", "as", "but", "or", "nor", "so", "yet", "a", "an"}
    LEGAL_ABBREVS = {"Dep't", "McDonald", "O'Connor", "Inc.", "LLC", "Co.", "Corp.", "Ltd.", "Assoc.", "Bros.", "Dr.", "Jr.", "Sr.", "St.", "Mt.", "Ft.", "Univ.", "Nat'l", "Fed.", "Comm'n", "Bd.", "Ctr.", "Dept.", "Hosp.", "Ctrs.", "Ctr.", "Ctrs.", "Ctrs."}
    CASE_NAME_PATTERNS = [r"v\.\s*", r"vs\.\s*", r"in re\s*", r"ex parte\s*", r"ex rel\.\s*"]
    REPORTER_ABBRS = {"Wn.2d", "Wn.", "F.3d", "F.2d", "F. Supp.", "F.", "P.3d", "P.2d", "P.", "U.S.", "S. Ct.", "L. Ed.", "Cal.", "N.Y.", "A.2d", "A.3d", "A.", "So.2d", "So.3d", "So.", "N.E.2d", "N.E.", "N.W.2d", "N.W.", "S.E.2d", "S.E.", "S.W.2d", "S.W.", "Ill.", "Tex.", "Ohio St.", "Mass.", "Colo.", "Wash.", "Minn.", "Kan.", "Okla.", "Md.", "Va.", "Pa.", "Ga.", "Ark.", "Wis.", "Mich.", "Ind.", "La.", "Mo.", "Tenn.", "Conn.", "N.J.", "Or.", "Iowa", "Neb.", "Nev.", "Mont.", "Idaho", "Utah", "Ala.", "Del.", "Haw.", "Ky.", "Me.", "N.M.", "N.D.", "R.I.", "S.D.", "Vt.", "W. Va.", "Wy.", "D.C.", "App.", "Cir.", "Ct.", "Ch.", "Bd.", "Div.", "Dept.", "Dist.", "Mun.", "Prob.", "Super.", "Supp.", "Tax.", "Tr.", "Juv.", "Fam.", "Mag.", "Com.", "Comr.", "Ref.", "Sm. Cl.", "Small Cl.", "Civ.", "Crim.", "Misc.", "Spec.", "En Banc"}
    n = len(citations)
    i = 0
    while i < n:
        c = citations[i]
        context = getattr(c, 'context', '') or ''
        citation_str = getattr(c, 'citation', '')
        citation_escaped = re.escape(citation_str)
        cite_pos = context.find(citation_str)
        if cite_pos == -1:
            context_for_case = context
        else:
            # Scan backwards for start
            pre = context[:cite_pos]
            words = list(re.finditer(r"\b\w+\b", pre))
            start_idx = len(words) - 1
            while start_idx >= 0:
                w = words[start_idx].group(0)
                if (not w[0].isupper()) and (w.lower() not in STOPWORDS):
                    break
                start_idx -= 1
            # Move forward to the next capitalized word
            start_idx += 1
            while start_idx < len(words) and not words[start_idx].group(0)[0].isupper():
                start_idx += 1
            if start_idx < len(words):
                start_pos = words[start_idx].start()
            else:
                start_pos = 0
            # Scan forward for end
            post = context[cite_pos:]
            # Look for a year in parentheses (1700-2099) not part of a citation
            year_match = re.search(r"\((17|18|19|20)\d{2}\)", post)
            # Look for the next citation (volume + reporter + page)
            next_cite_match = re.search(r"\b\d{1,4}\s+[A-Za-z.]+(?:\s+\d+)?\b", post)
            # Default end: 100 chars after citation
            default_end = min(len(post), len(citation_str) + 100)
            end_pos = cite_pos + default_end
            if year_match:
                # Make sure year is not part of a citation (not immediately preceded by a number and reporter)
                before_year = post[:year_match.start()]
                if not re.search(r"\d{1,4}\s+[A-Za-z.]+\s*$", before_year):
                    end_pos = cite_pos + year_match.end()
            if next_cite_match and (cite_pos + next_cite_match.start() < end_pos):
                end_pos = cite_pos + next_cite_match.start()
            context_for_case = context[start_pos:end_pos]
        log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, 'debug_prints.txt'), 'a', encoding='utf-8') as dbg:
            dbg.write(f"[DEBUG] Citation: {citation_str}\n[DEBUG] Context:\n{context_for_case}\n---\n")
        matches = list(re.finditer(r"([A-Z][A-Za-z0-9&.,'\- ]+?)\s*,\s*" + citation_escaped, context_for_case))
        if matches:
            last_match = matches[-1]
            filtered_case_name = last_match.group(1).strip()
            with open(os.path.join(log_dir, 'debug_prints.txt'), 'a', encoding='utf-8') as dbg:
                dbg.write(f"[DEBUG] Regex match: '{last_match.group(0)}' -> case name: '{filtered_case_name}'\n")
        else:
            filtered_case_name = None
            with open(os.path.join(log_dir, 'debug_prints.txt'), 'a', encoding='utf-8') as dbg:
                dbg.write(f"[DEBUG] No case name match for citation: {citation_str}\n")
        if filtered_case_name:
            # Start a group
            group = [c]
            date = getattr(c, 'extracted_date', None)
            j = i + 1
            while j < n:
                next_c = citations[j]
                next_context = getattr(next_c, 'context', '') or ''
                next_citation_str = getattr(next_c, 'citation', '')
                next_citation_escaped = re.escape(next_citation_str)
                next_case_name_match = re.search(r"([A-Z][A-Za-z0-9&.,'\- ]+?)\s*,\s*" + next_citation_escaped, next_context)
                if next_case_name_match:
                    break
                group.append(next_c)
                j += 1
            last_c = group[-1]
            last_context = getattr(last_c, 'context', '') or ''
            year_match = re.search(r"\((\d{4})\)", last_context)
            year = year_match.group(1) if year_match else getattr(last_c, 'extracted_date', None)
            # Assign filtered case name and year to all in group
            if filtered_case_name and year:
                for gc in group:
                    gc.extracted_case_name = filtered_case_name
                    gc.extracted_date = year
            i = j
        else:
            i += 1
    # --- NEW: For each group of adjacent citations with the same date, propagate case name from first and year from last ---
    n = len(citations)
    i = 0
    while i < n:
        # Start of a potential group
        group = [citations[i]]
        date = getattr(citations[i], 'extracted_date', None)
        j = i + 1
        while j < n:
            next_date = getattr(citations[j], 'extracted_date', None)
            if next_date == date:
                group.append(citations[j])
                j += 1
            else:
                break
        if len(group) > 1 and date:
            # Try to get case name from first, year from last
            first_case_name = getattr(group[0], 'extracted_case_name', None)
            last_year = getattr(group[-1], 'extracted_date', None)
            # If at least one has a case name and one has a year, propagate
            if first_case_name and last_year:
                for c in group:
                    c.extracted_case_name = first_case_name
                    c.extracted_date = last_year
        i = j
    # Debug output: show extracted case name and date for every citation after propagation
    import logging
    logger = logging.getLogger(__name__)
    for c in citations:
        logger.debug(f"[PROPAGATION DEBUG] Citation: {getattr(c, 'citation', None)}, extracted_case_name: {getattr(c, 'extracted_case_name', None)}, extracted_date: {getattr(c, 'extracted_date', None)}")
    logger.debug(f"[DEBUG] clusters_by_id keys: {list(clusters_by_id.keys())}")
    for cid, members in clusters_by_id.items():
        member_citations = []
        for c in members:
            if hasattr(c, 'citation'):
                member_citations.append(c.citation)
            elif isinstance(c, dict):
                member_citations.append(c.get('citation', ''))
            else:
                member_citations.append(str(c))
        logger.debug(f"[DEBUG] Cluster {cid}: {member_citations}")
    logger.debug(f"[DEBUG] clusters_by_id full: {clusters_by_id}")
    # --- FALLBACK: Group by extracted case name and date if not already clustered ---
    fallback_clusters = {}
    already_in_nonempty_cluster = set()
    # Track all citations already in a non-empty canonical or parallel cluster
    for cluster_citations in clusters_by_id.values():
        if cluster_citations:
            for c in cluster_citations:
                already_in_nonempty_cluster.add(getattr(c, 'citation', None))
    def normalize_case_name_for_key(name):
        if not name:
            return None
        import re
        # Remove everything after the first comma followed by a number (e.g., ', 200 Wn.2d 72')
        name = re.split(r',\s*\d', name)[0]
        # Remove everything after the first parenthesis
        name = re.split(r'\(', name)[0]
        return name.strip().lower()
    print("[DEBUG] Normalized extracted_case_name and extracted_date for all citations:")
    for citation in citations:
        extracted_name = getattr(citation, 'extracted_case_name', None)
        extracted_date = getattr(citation, 'extracted_date', None)
        norm_name = normalize_case_name_for_key(extracted_name)
        norm_date = str(extracted_date).strip() if extracted_date else None
        print(f"  Citation: {getattr(citation, 'citation', None)} | norm_name: {norm_name} | norm_date: {norm_date}")
    for citation in citations:
        # Only skip if already in a non-empty canonical or parallel cluster
        if getattr(citation, 'citation', None) in already_in_nonempty_cluster:
            continue
        # Use normalized extracted case name and date for fallback clustering
        extracted_name = getattr(citation, 'extracted_case_name', None)
        extracted_date = getattr(citation, 'extracted_date', None)
        norm_name = normalize_case_name_for_key(extracted_name)
        norm_date = str(extracted_date).strip() if extracted_date else None
        if norm_name and norm_date:
            key = (norm_name, norm_date)
            if key not in fallback_clusters:
                fallback_clusters[key] = []
            fallback_clusters[key].append(citation)
    print("[DEBUG] Fallback cluster keys and members:")
    for key, members in fallback_clusters.items():
        print(f"  Key: {key} | Members: {[getattr(m, 'citation', None) for m in members]}")
    logger.debug(f"[FALLBACK CLUSTERING] Keys: {list(fallback_clusters.keys())}")
    for key, members in fallback_clusters.items():
        logger.debug(f"[FALLBACK CLUSTERING] Key: {key}, Members: {[getattr(m, 'citation', None) for m in members]}")
    # Assign fallback clusters
    for key, members in fallback_clusters.items():
        if len(members) > 1:
            cluster_id = f"fallback_extracted_{key[0]}_{key[1]}"
            if cluster_id not in clusters_by_id:
                clusters_by_id[cluster_id] = []
            from collections import Counter
            original_names = [getattr(c, 'extracted_case_name', None) for c in members if getattr(c, 'extracted_case_name', None)]
            if original_names:
                best_name, _ = Counter(original_names).most_common(1)[0]
            else:
                best_name = None
            for citation in members:
                if hasattr(citation, 'extracted_case_name') and best_name:
                    old_name = getattr(citation, 'extracted_case_name', None)
                    if not old_name or old_name.strip() == '' or old_name == 'N/A':
                        citation.extracted_case_name = best_name
                    else:
                        # Debug print if overwriting
                        if citation.citation == '136 Wn. App. 104' and old_name != best_name:
                            print(f"[DEBUG] Overwriting extracted_case_name for 136 Wn. App. 104: '{old_name}' -> '{best_name}'")
                if hasattr(citation, 'extracted_date'):
                    citation.extracted_date = key[1]
                if hasattr(citation, 'metadata'):
                    citation.metadata = citation.metadata or {}
                    citation.metadata['is_in_cluster'] = True
                    citation.metadata['cluster_id'] = cluster_id
                elif isinstance(citation, dict):
                    citation.setdefault('metadata', {})
                    citation['metadata']['is_in_cluster'] = True
                    citation['metadata']['cluster_id'] = cluster_id
                if citation not in clusters_by_id[cluster_id]:
                    clusters_by_id[cluster_id].append(citation)
    # Ensure all clusters in clusters_by_id are included in result_clusters
    result_clusters = []
    clustered_citations = set()
    for cluster_id, cluster_citations in clusters_by_id.items():
        try:
            print(f"[DEBUG] Adding cluster to result_clusters: {cluster_id} | Members: {[getattr(c, 'citation', None) for c in cluster_citations]}")
            if not cluster_citations:
                continue
            # Get cluster metadata from the first citation
            first_citation = cluster_citations[0]
            if hasattr(first_citation, 'metadata') and first_citation.metadata:
                cluster_metadata = first_citation.metadata
            elif isinstance(first_citation, dict):
                cluster_metadata = first_citation.get('metadata', {})
            else:
                cluster_metadata = {}
            # Find the first verified citation in document order for cluster-level metadata
            sorted_citations = sorted(cluster_citations, key=lambda c: getattr(c, 'start_index', 0) if hasattr(c, 'start_index') and c.start_index is not None else 0)
            def is_citation_verified(citation):
                verified = getattr(citation, 'verified', False)
                if isinstance(verified, str):
                    return verified.lower() == 'true'
                return bool(verified)
            first_verified = next((c for c in sorted_citations if is_citation_verified(c)), None)
            best_citation = first_verified if first_verified else sorted_citations[0]
            is_verified = getattr(best_citation, 'verified', False)
            if isinstance(is_verified, str):
                is_verified = is_verified.lower() == 'true'
            cluster_canonical_name = getattr(best_citation, 'canonical_name', None) if is_verified else getattr(best_citation, 'canonical_name', None)
            cluster_canonical_date = getattr(best_citation, 'canonical_date', None) if is_verified else getattr(best_citation, 'canonical_date', None)
            cluster_extracted_case_name = getattr(best_citation, 'extracted_case_name', None)
            cluster_extracted_date = getattr(best_citation, 'extracted_date', None)
            cluster_url = getattr(best_citation, 'url', None) if is_verified else getattr(best_citation, 'url', None)
            citation_dicts = []
            any_verified = any(is_citation_verified(c) for c in cluster_citations)
            for citation in cluster_citations:
                clustered_citations.add(getattr(citation, 'citation', None))
                if hasattr(citation, 'citation'):
                    citation_dict = {
                        'citation': citation.citation,
                        'extracted_case_name': citation.extracted_case_name or 'N/A',
                        'extracted_date': citation.extracted_date or 'N/A',
                        'canonical_name': citation.canonical_name or 'N/A',
                        'canonical_date': citation.canonical_date,
                        'confidence': citation.confidence,
                        'source': citation.source,
                        'url': citation.url,
                        'court': citation.court,
                        'context': citation.context,
                        'verified': citation.verified,
                        'parallel_citations': citation.parallel_citations or []
                    }
                    if not citation.verified and any_verified:
                        citation_dict['true_by_parallel'] = True
                else:
                    citation_dict = citation
                    if not citation.get('verified', False) and any_verified:
                        citation_dict['true_by_parallel'] = True
                citation_dicts.append(citation_dict)
            cluster_dict = {
                'cluster_id': cluster_id,
                'canonical_name': cluster_canonical_name or cluster_extracted_case_name,
                'canonical_date': cluster_canonical_date or cluster_extracted_date,
                'extracted_case_name': cluster_extracted_case_name,
                'extracted_date': cluster_extracted_date,
                'url': cluster_url,
                'source': 'citation_clustering',
                'citations': citation_dicts,
                'has_parallel_citations': len(citation_dicts) > 1,
                'size': len(citation_dicts)
            }
            result_clusters.append(cluster_dict)
        except Exception as e:
            logger.error(f"[ERROR] Exception while formatting cluster {cluster_id}: {e}")
            logger.error(f"[ERROR] Cluster citations: {cluster_citations}")
            import traceback; traceback.print_exc()
    # NEW: Add singleton clusters for any citation not already in a cluster
    all_citations_set = set(getattr(c, 'citation', None) for c in citations)
    for citation in citations:
        if getattr(citation, 'citation', None) not in clustered_citations:
            # Build a singleton cluster
            cluster_id = f"singleton_{getattr(citation, 'citation', 'unknown')}"
            cluster_dict = {
                'cluster_id': cluster_id,
                'canonical_name': citation.canonical_name or citation.extracted_case_name,
                'canonical_date': citation.canonical_date or citation.extracted_date,
                'extracted_case_name': citation.extracted_case_name,
                'extracted_date': citation.extracted_date,
                'url': citation.url,
                'source': citation.source,
                'citations': [{
                    'citation': citation.citation,
                    'extracted_case_name': citation.extracted_case_name or 'N/A',
                    'extracted_date': citation.extracted_date or 'N/A',
                    'canonical_name': citation.canonical_name or 'N/A',
                    'canonical_date': citation.canonical_date,
                    'confidence': citation.confidence,
                    'source': citation.source,
                    'url': citation.url,
                    'court': citation.court,
                    'context': citation.context,
                    'verified': citation.verified,
                    'parallel_citations': citation.parallel_citations or []
                }],
                'has_parallel_citations': False,
                'size': 1
            }
            result_clusters.append(cluster_dict)
    return result_clusters

def _merge_parallel_clusters(clusters: dict, cluster_meta: dict) -> dict:
    """
    Merge clusters that contain parallel citations to the same case.
    This version finds all connected components in the citation-parallel graph and merges them into single clusters.
    Ensures all parallel_citations relationships are symmetric.
    Also merges base citations (without page numbers) with their corresponding full citations.
    """
    # Build a mapping from citation string to (cluster key, member)
    citation_to_key_member = {}
    for key, members in clusters.items():
        for member in members:
            citation_to_key_member[member.citation] = (key, member)

    # Build undirected graph of all citations and their parallels, enforcing symmetry
    graph = defaultdict(set)
    # First pass: add all edges
    for citation, (key, member) in citation_to_key_member.items():
        graph[citation]  # ensure node exists
        for parallel in member.parallel_citations or []:
            graph[citation].add(parallel)
    # Second pass: enforce symmetry
    for citation in list(graph.keys()):
        for parallel in list(graph[citation]):
            graph[parallel].add(citation)

    # Find all connected components (each is a cluster)
    visited = set()
    components = []
    for citation in graph:
        if citation not in visited:
            queue = deque([citation])
            component = set()
            while queue:
                node = queue.popleft()
                if node not in visited:
                    visited.add(node)
                    component.add(node)
                    queue.extend(graph[node] - visited)
            components.append(component)

    # For citations not in any parallel group, add as their own component
    all_citations = set(citation_to_key_member.keys())
    covered = set().union(*components) if components else set()
    for citation in all_citations - covered:
        components.append({citation})

    # Merge all citations in each component into a single cluster
    merged_clusters = {}
    merged_meta = {}
    for i, component in enumerate(components):
        merged = []
        for citation in component:
            _, member = citation_to_key_member[citation]
            merged.append(member)
        # Remove duplicates while preserving order
        seen = set()
        merged_unique = []
        for m in merged:
            if m.citation not in seen:
                merged_unique.append(m)
                seen.add(m.citation)
        cluster_key = f"component_{i}"
        merged_clusters[cluster_key] = merged_unique
        # Assign best available metadata (prefer canonical, then extracted)
        best = None
        for m in merged_unique:
            if m.canonical_name and m.canonical_name != 'N/A':
                best = m
                break
        if not best:
            for m in merged_unique:
                if m.extracted_case_name and m.extracted_case_name != 'N/A':
                    best = m
                    break
        if not best and merged_unique:
            best = merged_unique[0]
        if best:
            merged_meta[cluster_key] = {
                'canonical_name': best.canonical_name,
                'canonical_date': best.canonical_date,
                'extracted_case_name': best.extracted_case_name,
                'extracted_date': best.extracted_date,
                'url': best.url,
                'source': best.source
            }
        else:
            merged_meta[cluster_key] = {}

    # Post-process: merge base citations (without page numbers) with their corresponding full citations
    # Build a mapping from base citation to all clusters containing full citations
    base_to_full_clusters = {}
    for cluster_key, members in merged_clusters.items():
        for member in members:
            base_citation = member.citation.split()[0] if member.citation else ''
            if base_citation != member.citation:
                if base_citation not in base_to_full_clusters:
                    base_to_full_clusters[base_citation] = set()
                base_to_full_clusters[base_citation].add(cluster_key)

    # Now, for every cluster that contains only a base citation, merge it into all clusters with the corresponding full citation
    clusters_to_remove = set()
    for cluster_key, members in list(merged_clusters.items()):
        if len(members) == 1:
            member = members[0]
            base_citation = member.citation.split()[0] if member.citation else ''
            if base_citation == member.citation and base_citation in base_to_full_clusters:
                for full_cluster_key in base_to_full_clusters[base_citation]:
                    if full_cluster_key != cluster_key:
                        merged_clusters[full_cluster_key].append(member)
                clusters_to_remove.add(cluster_key)

    # Remove merged base-only clusters
    for cluster_key in clusters_to_remove:
        merged_clusters.pop(cluster_key, None)
        merged_meta.pop(cluster_key, None)

    # Update cluster_meta with merged_meta
    cluster_meta.clear()
    cluster_meta.update(merged_meta)
    return merged_clusters

def _is_citation_contained_in_any(citation_str: str, existing_citations: set) -> bool:
    """
    Check if a citation is contained within any existing citation.
    For example: '200 Wn.2d' is contained in '200 Wn.2d 72'
    """
    # Normalize the citation for comparison
    norm_citation = citation_str.strip()
    
    for existing in existing_citations:
        norm_existing = existing.strip()
        # Check if the new citation is a prefix of an existing citation
        # and the existing citation has additional content (like page numbers)
        if norm_citation in norm_existing and len(norm_existing) > len(norm_citation):
            # Additional check: make sure it's not just a coincidence
            # The existing citation should have additional meaningful content
            remaining = norm_existing[len(norm_citation):].strip()
            if remaining and any(c.isdigit() for c in remaining):
                return True
    return False

def _apply_fallback_clustering(citations: List[CitationResult], text: str) -> None:
    """
    DEPRECATED: Use isolation-aware clustering logic instead.
    Apply fallback clustering using the original algorithm.
    """
    warnings.warn(
        "_apply_fallback_clustering is deprecated. Use isolation-aware clustering instead.",
        DeprecationWarning,
        stacklevel=2
    )
    # (Original fallback clustering logic would go here)
    pass

def _propagate_canonical_to_parallels(citations: List['CitationResult']):
    """
    Propagate canonical name and date to all parallel citations in the group.
    """
    for citation in citations:
        if citation.parallel_citations:
            for parallel in citation.parallel_citations:
                for other in citations:
                    if other.citation == parallel:
                        if citation.canonical_name and not other.canonical_name:
                            other.canonical_name = citation.canonical_name
                        if citation.canonical_date and not other.canonical_date:
                            other.canonical_date = citation.canonical_date

def _propagate_extracted_to_parallels(citations: List['CitationResult']):
    """
    Propagate extracted case name and date to all parallel citations in the group.
    """
    for citation in citations:
        if citation.parallel_citations:
            for parallel in citation.parallel_citations:
                for other in citations:
                    if other.citation == parallel:
                        if citation.extracted_case_name and not other.extracted_case_name:
                            other.extracted_case_name = citation.extracted_case_name
                        if citation.extracted_date and not other.extracted_date:
                            other.extracted_date = citation.extracted_date

def _propagate_best_extracted_to_clusters(citations: list):
    """
    Propagate the best extracted case name and date to all citations in a cluster.
    """
    def is_valid_name(name):
        if not name or name == 'N/A':
            return False
        if len(name) < 5:
            return False
        if not any(c.isalpha() for c in name):
            return False
        return True

    # Forward propagation
    for i, citation in enumerate(citations):
        if not is_valid_name(getattr(citation, 'extracted_case_name', None)):
            for j, other in enumerate(citations):
                if i == j:
                    continue
                if hasattr(other, 'start_index') and hasattr(citation, 'end_index') and other.start_index is not None and citation.end_index is not None:
                    if 0 <= other.start_index - citation.end_index <= 100:
                        if is_valid_name(getattr(other, 'extracted_case_name', None)):
                            citation.extracted_case_name = other.extracted_case_name
                        if getattr(other, 'extracted_date', None) and getattr(other, 'extracted_date', None) != 'N/A':
                            citation.extracted_date = other.extracted_date
    # Backward propagation
    for i, citation in enumerate(citations):
        if not is_valid_name(getattr(citation, 'extracted_case_name', None)):
            for j, other in enumerate(citations):
                if i == j:
                    continue
                if hasattr(other, 'start_index') and hasattr(citation, 'end_index') and other.start_index is not None and citation.end_index is not None:
                    if 0 <= other.start_index - citation.end_index <= 100:
                        if is_valid_name(getattr(other, 'extracted_case_name', None)):
                            citation.extracted_case_name = other.extracted_case_name
                        if getattr(other, 'extracted_date', None) and getattr(other, 'extracted_date', None) != 'N/A':
                            citation.extracted_date = other.extracted_date 