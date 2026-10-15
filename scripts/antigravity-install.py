#!/usr/bin/env python3
"""
Install skills from claude-skills into Antigravity.

Supports:
- Global installation to ~/.gemini/config/skills/ (available across all projects)
- Workspace installation to .agents/skills/ (project-specific)
- Filtering by category/domain, specific skill name, or installing all.

Usage examples:
    python scripts/antigravity-install.py --list
    python scripts/antigravity-install.py --domain engineering
    python scripts/antigravity-install.py --skill senior-architect
    python scripts/antigravity-install.py --all
    python scripts/antigravity-install.py --domain engineering --scope workspace
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional


DOMAIN_MAP = {
    "marketing-skill": "marketing",
    "engineering-team": "engineering",
    "engineering": "engineering-advanced",
    "product-team": "product",
    "c-level-advisor": "c-level",
    "project-management": "project-management",
    "ra-qm-team": "ra-qm",
    "business-growth": "business-growth",
    "finance": "finance",
    "productivity": "productivity",
    "marketing": "marketing-top-level",
    "research": "research",
    "business-operations": "business-operations",
    "commercial": "commercial",
    "research-ops": "research-ops",
    "compliance-os": "compliance-os",
    "markdown-html": "markdown-html",
    "agent-launcher": "agent-launcher",
}


def extract_frontmatter(file_path: Path) -> Dict[str, str]:
    """Extract name and description from YAML frontmatter."""
    try:
        content = file_path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return {}
        end_idx = content.find("---", 3)
        if end_idx == -1:
            return {}
        fm = {}
        for line in content[3:end_idx].split("\n"):
            line = line.strip()
            if line.startswith("name:"):
                fm["name"] = line[5:].strip().strip("\"'")
            elif line.startswith("description:"):
                desc = line[12:].strip().strip("\"'")
                fm["description"] = desc
        return fm
    except Exception:
        return {}


def discover_skills(repo_root: Path) -> List[Dict]:
    """Discover all installable skills, agents, and commands."""
    skills = []
    seen_names = set()

    # 1. Real skill folders containing SKILL.md
    for skill_md in repo_root.rglob("SKILL.md"):
        parts = skill_md.parts
        if ".gemini" in parts or ".codex" in parts or ".claude" in parts or ".hermes" in parts or ".vibe" in parts:
            continue
        if "eval-workspace" in parts or "assets" in parts or "evals" in parts:
            if "sample-skill" not in parts:
                continue

        top_level = skill_md.relative_to(repo_root).parts[0]
        if top_level not in DOMAIN_MAP and top_level not in ("agents", "commands"):
            continue

        skill_dir = skill_md.parent
        if skill_dir == repo_root:
            continue

        if skill_dir.name in DOMAIN_MAP:
            skill_name = f"{skill_dir.name}-bundle"
        else:
            skill_name = skill_dir.name

        if skill_name in seen_names:
            candidate = f"{skill_dir.parent.name}-{skill_name}"
            n = 2
            base = candidate
            while candidate in seen_names:
                candidate = f"{base}-{n}"
                n += 1
            skill_name = candidate

        seen_names.add(skill_name)

        category = "general"
        for folder, cat in DOMAIN_MAP.items():
            if folder in parts:
                category = cat
                break

        fm = extract_frontmatter(skill_md)
        description = fm.get("description", f"Skill from {skill_dir.name}")

        skills.append({
            "name": skill_name,
            "category": category,
            "type": "directory",
            "source_dir": skill_dir,
            "description": description,
        })

    # 2. Agents as Skills
    agents_path = repo_root / "agents"
    if agents_path.exists():
        for agent_file in agents_path.rglob("*.md"):
            if agent_file.name in ("CLAUDE.md", "README.md", "TEMPLATE.md", "template.md") or ".gemini" in agent_file.parts:
                continue
            agent_name = agent_file.stem
            if agent_name in seen_names:
                agent_name = f"agent-{agent_name}"
            seen_names.add(agent_name)

            fm = extract_frontmatter(agent_file)
            skills.append({
                "name": agent_name,
                "category": "agent",
                "type": "file",
                "source_file": agent_file,
                "description": fm.get("description", f"Agent persona {agent_name}"),
            })

    # 3. Commands as Skills
    commands_path = repo_root / "commands"
    if commands_path.exists():
        for cmd_file in commands_path.glob("*.md"):
            if cmd_file.name == ".gitkeep":
                continue
            cmd_name = cmd_file.stem
            if cmd_name in seen_names:
                cmd_name = f"cmd-{cmd_name}"
            seen_names.add(cmd_name)

            fm = extract_frontmatter(cmd_file)
            skills.append({
                "name": cmd_name,
                "category": "command",
                "type": "file",
                "source_file": cmd_file,
                "description": fm.get("description", f"Slash command {cmd_name}"),
            })

    skills.sort(key=lambda s: (s["category"], s["name"]))
    return skills


def install_skill(skill: Dict, dest_dir: Path) -> bool:
    """Install a skill into dest_dir/skill['name']."""
    target_path = dest_dir / skill["name"]
    target_path.mkdir(parents=True, exist_ok=True)

    if skill["type"] == "directory":
        src = skill["source_dir"]
        for item in src.iterdir():
            dst = target_path / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
        return True
    elif skill["type"] == "file":
        src = skill["source_file"]
        content = src.read_text(encoding="utf-8")
        # Ensure it has frontmatter
        if not content.startswith("---"):
            content = f"---\nname: {skill['name']}\ndescription: \"{skill['description']}\"\n---\n\n" + content
        (target_path / "SKILL.md").write_text(content, encoding="utf-8")
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Install claude-skills into Antigravity")
    parser.add_argument("--scope", choices=["global", "workspace"], default="global",
                        help="Installation scope: 'global' (~/.gemini/config/skills) or 'workspace' (.agents/skills)")
    parser.add_argument("--target-dir", type=str, default=None,
                        help="Explicit target directory for skills")
    parser.add_argument("--all", action="store_true", help="Install all skills")
    parser.add_argument("--domain", "--category", dest="domain", type=str,
                        help="Install all skills in a specific domain/category (e.g. engineering, product, c-level)")
    parser.add_argument("--skill", type=str, help="Install a specific skill by name")
    parser.add_argument("--list", action="store_true", help="List available categories and counts")
    parser.add_argument("--dry-run", action="store_true", help="Preview installation without copying files")

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    all_skills = discover_skills(repo_root)

    if args.list:
        print(f"\nAvailable Skills in repository ({len(all_skills)} total):\n")
        categories = {}
        for s in all_skills:
            categories.setdefault(s["category"], []).append(s)

        for cat, skills in sorted(categories.items()):
            print(f"  [{cat}] ({len(skills)} skills)")
            sample = [s["name"] for s in skills[:4]]
            if len(skills) > 4:
                sample.append(f"... +{len(skills) - 4} more")
            print(f"      Exemplos: {', '.join(sample)}")
        print("\nUse --domain <name> para instalar uma categoria ou --skill <nome> para uma skill individual.\n")
        return

    # Determine target directory
    if args.target_dir:
        dest_dir = Path(args.target_dir)
    elif args.scope == "global":
        dest_dir = Path.home() / ".gemini" / "config" / "skills"
    else:
        dest_dir = repo_root / ".agents" / "skills"

    # Filter skills
    to_install = []
    if args.skill:
        to_install = [s for s in all_skills if s["name"].lower() == args.skill.lower()]
        if not to_install:
            print(f"Error: Skill '{args.skill}' not found.")
            sys.exit(1)
    elif args.domain:
        domain_query = args.domain.lower()
        to_install = [s for s in all_skills if domain_query in s["category"].lower()]
        if not to_install:
            print(f"Error: Domain '{args.domain}' not found. Use --list to see available domains.")
            sys.exit(1)
    elif args.all:
        to_install = all_skills
    else:
        print("Aviso: Especifique --all, --domain <categoria>, --skill <nome> ou --list.")
        print("Exemplo: python scripts/antigravity-install.py --domain engineering")
        sys.exit(1)

    print(f"\nInstalando {len(to_install)} skill(s) em:")
    print(f"  Destino: {dest_dir} (Escopo: {args.scope})")

    if args.dry_run:
        print("[DRY RUN] Nenhuma alteração feita no disco.")
        for s in to_install[:10]:
            print(f"  - {s['name']} ({s['category']})")
        if len(to_install) > 10:
            print(f"  ... e mais {len(to_install) - 10} skills")
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    installed = 0
    for s in to_install:
        try:
            if install_skill(s, dest_dir):
                installed += 1
        except Exception as e:
            print(f"Erro ao instalar {s['name']}: {e}")

    print(f"\n[SUCESSO] {installed}/{len(to_install)} skills instaladas com sucesso no Antigravity!")
    print(f"As skills instaladas estão prontas para serem ativadas no seu Antigravity.")


if __name__ == "__main__":
    main()
