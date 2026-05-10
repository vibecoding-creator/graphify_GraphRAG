import re
import json
import os
import sys
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
import graphify.export as ge

target_file = sys.argv[1] if len(sys.argv) > 1 else "3f_report.md"
text = open(target_file, "r", encoding="utf-8").read()

nodes = []
edges = []
seen_nodes = set()

def add_node(id_str, label, file_type="document", source_location=None, doc_title=None):
    # 한글 및 알파벳, 숫자를 허용하도록 정규식 수정
    id_str = re.sub(r'[^a-z0-9_가-힣]', '_', id_str.lower().strip())
    if not id_str: return None

    if id_str not in seen_nodes:
        nodes.append({
            "id": id_str,
            "label": label[:150] + ("..." if len(label)>150 else ""),
            "file_type": file_type,
            "source_file": f"{source_location or '-'}__SPLIT__{doc_title or '-'}"
        })
        seen_nodes.add(id_str)
    return id_str

def add_edge(src, tgt, relation):
    if src and tgt:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": target_file,
            "weight": 1.0
        })

doc_title_match = re.search(r'^# (.*)', text, re.MULTILINE)
doc_title = doc_title_match.group(1).strip() if doc_title_match else target_file
# Ensure doc_title has an extension so graphify.analyze doesn't filter nodes as 'concept nodes'
if not doc_title.lower().endswith(".md"):
    doc_title += ".md"

slides = text.split("## Slide ")
for slide in slides[1:]:
    slide_num = slide.split("\n")[0].strip()
    rows = {}
    lines = slide.split("\n")
    current_key = None
    current_row = None
    
    for line in lines:
        match = re.match(r'### (.*?) \((row\d+)\)', line)
        if match:
            current_key = match.group(1).strip()
            current_row = match.group(2).strip()
            if current_row not in rows:
                rows[current_row] = {}
            rows[current_row][current_key] = []
        elif current_key and current_row and line.strip().startswith("- "):
            rows[current_row][current_key].append(line.replace("- ", "").strip())
            
    for row_name, data in rows.items():
        problem_text = " ".join(data.get("Problem", []))
        cause_text = " ".join(data.get("Solution_Cause", []))
        solution_text = " ".join(data.get("Solution_What/How", []))
        owner_text = " ".join(data.get("Solution_Owner", []))
        
        if not problem_text: continue
        
        loc = "Slide " + slide_num
        
        prob_id = add_node("prob_" + slide_num + "_" + row_name, "[문제] " + problem_text, "rationale", loc, doc_title)
        
        if cause_text and cause_text != "(empty)" and cause_text != "-":
            cause_id = add_node("cause_" + slide_num + "_" + row_name, "[원인] " + cause_text, "rationale", loc, doc_title)
            add_edge(prob_id, cause_id, "has_cause")
            
        if solution_text and solution_text != "(empty)" and solution_text != "-":
            sol_id = add_node("sol_" + slide_num + "_" + row_name, "[해결책] " + solution_text, "rationale", loc, doc_title)
            add_edge(prob_id, sol_id, "has_solution")
            
            if owner_text and owner_text != "(empty)" and owner_text != "-":
                owners = [o.strip() for o in owner_text.replace("(", "").replace(")", "").split() if len(o)>1]
                for o in owners:
                    owner_id = add_node("owner_" + o, "[담당자] " + o, "document", loc, doc_title)
                    add_edge(sol_id, owner_id, "assigned_to")

output = {
    "nodes": nodes,
    "edges": edges,
    "hyperedges": [],
    "input_tokens": 0,
    "output_tokens": 0
}

os.makedirs("graphify-out", exist_ok=True)
Path("graphify-out/.graphify_extract.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Extracted {len(nodes)} nodes and {len(edges)} edges from {target_file}")

G = build_from_json(output)
communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: 'Community ' + str(cid) for cid in communities}
questions = suggest_questions(G, communities, labels)

ge.to_json(G, communities, 'graphify-out/graph.json')

# Fake detection dictionary to prevent KeyError
fake_detection = {'total_files': 1, 'total_words': 1000}

report = generate(G, communities, cohesion, labels, gods, surprises, fake_detection, {'input':0, 'output':0}, target_file, suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report, encoding="utf-8")

analysis = {
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {str(k): v for k, v in cohesion.items()},
    'gods': gods,
    'surprises': surprises,
    'questions': questions,
}
Path('graphify-out/.graphify_analysis.json').write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
print("Graph successfully built.")
