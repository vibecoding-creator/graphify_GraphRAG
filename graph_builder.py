import os
import shutil
import subprocess
import sys

GLOBAL_GRAPH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "global_graph")

def build_graph(input_md_path: str, output_dir: str, run_id: str = None):
    """
    Runs the full graphify pipeline on the given markdown file.
    output_dir will be used as the working directory to isolate runs.
    input_md_path must already be located inside output_dir as 'input.md'.
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(GLOBAL_GRAPH_DIR, exist_ok=True)

    # 1. Copy only the helper scripts into the output_dir
    #    (input.md is already saved there by app.py)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    shutil.copy2(os.path.join(script_dir, "parse_3f_report.py"), output_dir)
    shutil.copy2(os.path.join(script_dir, "fix_html.py"), output_dir)

    target_md = "input.md"

    env = os.environ.copy()

    # 2. Run parse_3f_report.py
    subprocess.run([sys.executable, "parse_3f_report.py", target_md], cwd=output_dir, check=True, env=env)

    # 3. Generate labels (Community labels mapping)
    label_script = "import json; d = json.load(open('graphify-out/graph.json', encoding='utf-8')); communities = set(n.get('community') for n in d['nodes'] if 'community' in n); labels = {str(c): f'Community {c}' for c in communities}; open('graphify-out/.graphify_labels.json', 'w', encoding='utf-8').write(json.dumps(labels))"
    subprocess.run([sys.executable, "-c", label_script], cwd=output_dir, check=True, env=env)

    # 4. Export HTML using graphify CLI
    subprocess.run([sys.executable, "-m", "graphify", "export", "html"], cwd=output_dir, check=True, env=env)

    # 5. Fix HTML to separate Document and Slide + inject Global Graph button
    fix_args = [sys.executable, "fix_html.py"]
    if run_id:
        fix_args.append(run_id)
    subprocess.run(fix_args, cwd=output_dir, check=True, env=env)

    # 6. Copy .graphify_extract.json (원본 추출 포맷) to global_graph directory for merging
    #    graph.json은 networkx export 포맷이라 build_from_json()에 재사용 불가
    src_extract = os.path.join(output_dir, "graphify-out", ".graphify_extract.json")
    if run_id and os.path.exists(src_extract):
        shutil.copy2(src_extract, os.path.join(GLOBAL_GRAPH_DIR, f"{run_id}.json"))

    # The final HTML is now at output_dir/graphify-out/graph.html
    return os.path.join(output_dir, "graphify-out", "graph.html")
