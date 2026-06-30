"""Generate HTML reports for API diffs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Template

from .diff import (
    ApiDiff,
    doc_url,
    group_entries_by_namespace,
    group_member_diffs_by_namespace,
    split_namespace_class,
)

REPORT_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unity API Diff: {{ diff.from_version }} → {{ diff.to_version }}</title>
  <style>
    :root {
      --bg: #0f1419;
      --surface: #1a2332;
      --border: #2d3a4d;
      --text: #e6edf3;
      --muted: #8b9cb3;
      --added: #3fb950;
      --removed: #f85149;
      --changed: #d29922;
      --accent: #58a6ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }
    header {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 1.5rem 2rem;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    h1 { margin: 0 0 0.25rem; font-size: 1.5rem; }
    .subtitle { color: var(--muted); font-size: 0.9rem; }
    .stats {
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
      margin-top: 1rem;
    }
    .stat {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.75rem 1rem;
      min-width: 120px;
    }
    .stat .num { font-size: 1.5rem; font-weight: 700; }
    .stat.added .num { color: var(--added); }
    .stat.removed .num { color: var(--removed); }
    .stat.changed .num { color: var(--changed); }
    .controls {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      margin-top: 1rem;
      align-items: center;
    }
    input[type="search"] {
      flex: 1;
      min-width: 200px;
      padding: 0.5rem 0.75rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text);
      font-size: 0.95rem;
    }
    .tabs button {
      padding: 0.45rem 0.9rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text);
      cursor: pointer;
    }
    .tabs button.active {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    main { padding: 1.5rem 2rem 3rem; max-width: 1400px; margin: 0 auto; }
    section { display: none; }
    section.active { display: block; }
    .entry-list { list-style: none; padding: 0; margin: 0; }
    .entry {
      border: 1px solid var(--border);
      border-radius: 8px;
      margin-bottom: 0.5rem;
      background: var(--surface);
      overflow: hidden;
    }
    .entry-header {
      padding: 0.75rem 1rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
    }
    .entry-header a { color: var(--accent); text-decoration: none; }
    .entry-header a:hover { text-decoration: underline; }
    .badge {
      font-size: 0.75rem;
      padding: 0.15rem 0.5rem;
      border-radius: 999px;
      font-weight: 600;
      white-space: nowrap;
    }
    .badge.added { background: rgba(63,185,80,0.15); color: var(--added); }
    .badge.removed { background: rgba(248,81,73,0.15); color: var(--removed); }
    .badge.changed { background: rgba(210,153,34,0.15); color: var(--changed); }
    .path { color: var(--muted); font-size: 0.85rem; }
    .member-block {
      border-top: 1px solid var(--border);
      padding: 0.75rem 1rem 1rem;
      font-size: 0.9rem;
    }
    .member-group { margin-bottom: 0.75rem; }
    .member-group h4 { margin: 0 0 0.35rem; font-size: 0.85rem; color: var(--muted); }
    .namespace-group { margin-bottom: 2rem; }
    .namespace-group > h2 {
      font-size: 1.1rem;
      color: var(--accent);
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.35rem;
      margin: 0 0 0.75rem;
    }
    .class-name { font-weight: 600; }
    .member-item { margin-bottom: 0.5rem; }
    .member-item .sig-box { margin-top: 0.25rem; }
    .sig-compare {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.5rem;
      margin-top: 0.35rem;
    }
    .sig-box {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 0.5rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.8rem;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .sig-box.old { border-color: rgba(248,81,73,0.4); }
    .sig-box.new { border-color: rgba(63,185,80,0.4); }
    .empty { color: var(--muted); padding: 2rem; text-align: center; }
    footer {
      text-align: center;
      color: var(--muted);
      font-size: 0.8rem;
      padding: 2rem;
      border-top: 1px solid var(--border);
    }
    @media (max-width: 768px) {
      .sig-compare { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Unity Scripting API 差异报告</h1>
    <div class="subtitle">
      {{ diff.from_version }} → {{ diff.to_version }}
      · 生成于 {{ generated_at }}
      · 数据来源 <a href="https://docs.unity3d.com/ScriptReference/index.html" style="color:var(--accent)">Unity Scripting API</a>
    </div>
    <div class="stats">
      <div class="stat added"><div class="num">{{ summary.added }}</div>新增 API</div>
      <div class="stat removed"><div class="num">{{ summary.removed }}</div>移除 API</div>
      <div class="stat changed"><div class="num">{{ summary.changed_types }}</div>变更类型</div>
      <div class="stat changed"><div class="num">{{ summary.changed_members }}</div>成员级变更</div>
    </div>
    <div class="controls">
      <input type="search" id="search" placeholder="搜索 API 名称或路径...">
      <div class="tabs">
        <button class="active" data-tab="all">全部</button>
        <button data-tab="added">新增</button>
        <button data-tab="removed">移除</button>
        <button data-tab="changed">变更</button>
      </div>
    </div>
  </header>

  <main>
    <section id="tab-all" class="active">
      <h2>新增 ({{ summary.added }})</h2>
      {% for namespace, entries in grouped_added %}
      <div class="namespace-group">
        <h2>{{ namespace or '(全局)' }}</h2>
        <ul class="entry-list" data-kind="added">
          {% for entry in entries %}
          <li class="entry" data-search="{{ namespace }} {{ entry.link }} {{ entry.path }} {{ entry.title }}">
            <div class="entry-header">
              <div>
                <span class="class-name">{{ entry.title }}</span>
                <a href="{{ doc_url(diff.to_version, entry.link) }}" target="_blank">{{ entry.link }}</a>
                <div class="path">{{ entry.path }}</div>
              </div>
              <span class="badge added">新增</span>
            </div>
          </li>
          {% endfor %}
        </ul>
      </div>
      {% else %}
      <p class="empty">无新增 API</p>
      {% endfor %}

      <h2 style="margin-top:2rem">移除 ({{ summary.removed }})</h2>
      {% for namespace, entries in grouped_removed %}
      <div class="namespace-group">
        <h2>{{ namespace or '(全局)' }}</h2>
        <ul class="entry-list" data-kind="removed">
          {% for entry in entries %}
          <li class="entry" data-search="{{ namespace }} {{ entry.link }} {{ entry.path }} {{ entry.title }}">
            <div class="entry-header">
              <div>
                <span class="class-name">{{ entry.title }}</span>
                <a href="{{ doc_url(diff.from_version, entry.link) }}" target="_blank">{{ entry.link }}</a>
                <div class="path">{{ entry.path }}</div>
              </div>
              <span class="badge removed">移除</span>
            </div>
          </li>
          {% endfor %}
        </ul>
      </div>
      {% else %}
      <p class="empty">无移除 API</p>
      {% endfor %}

      <h2 style="margin-top:2rem">成员变更 ({{ summary.changed_types }})</h2>
      {% for namespace, type_diffs in grouped_changed %}
      <div class="namespace-group">
        <h2>{{ namespace or '(全局)' }}</h2>
        <ul class="entry-list" data-kind="changed">
          {% for td in type_diffs %}
          <li class="entry" data-search="{{ namespace }} {{ td.type_link }} {{ td.type_title }} {% for mi in td.added_members %}{{ mi.name }} {% for s in mi.signatures %}{{ s }} {% endfor %}{% endfor %}{% for mi in td.removed_members %}{{ mi.name }} {% for s in mi.signatures %}{{ s }} {% endfor %}{% endfor %}{% for mc in td.changed_members %}{{ mc.member_name }} {% for s in mc.old_signatures %}{{ s }} {% endfor %}{% for s in mc.new_signatures %}{{ s }} {% endfor %}{% endfor %}">
            <div class="entry-header">
              <div>
                <span class="class-name">{{ td.type_title }}</span>
                <a href="{{ doc_url(diff.to_version, td.type_link) }}" target="_blank">{{ td.type_link }}</a>
              </div>
              <span class="badge changed">变更</span>
            </div>
            <div class="member-block">
              {% if td.added_members %}
              <div class="member-group">
                <h4>新增成员 ({{ td.added_members|length }})</h4>
                <ul>
                  {% for mi in td.added_members %}
                  <li class="member-item">
                    <a href="{{ doc_url(diff.to_version, mi.member_link) }}" target="_blank">{{ mi.name }}</a>
                    {% if mi.signatures %}
                    <div class="sig-box new">{{ mi.signatures|join('\\n') }}</div>
                    {% endif %}
                  </li>
                  {% endfor %}
                </ul>
              </div>
              {% endif %}
              {% if td.removed_members %}
              <div class="member-group">
                <h4>移除成员 ({{ td.removed_members|length }})</h4>
                <ul>
                  {% for mi in td.removed_members %}
                  <li class="member-item">
                    <a href="{{ doc_url(diff.from_version, mi.member_link) }}" target="_blank">{{ mi.name }}</a>
                    {% if mi.signatures %}
                    <div class="sig-box old">{{ mi.signatures|join('\\n') }}</div>
                    {% endif %}
                  </li>
                  {% endfor %}
                </ul>
              </div>
              {% endif %}
              {% for mc in td.changed_members %}
              <div class="member-group">
                <h4>签名变更: <a href="{{ doc_url(diff.to_version, mc.member_link) }}" target="_blank">{{ mc.member_name }}</a></h4>
                <div class="sig-compare">
                  <div>
                    <div class="path">{{ diff.from_version }}</div>
                    <div class="sig-box old">{{ mc.old_signatures|join('\\n') or '(无签名)' }}</div>
                  </div>
                  <div>
                    <div class="path">{{ diff.to_version }}</div>
                    <div class="sig-box new">{{ mc.new_signatures|join('\\n') or '(无签名)' }}</div>
                  </div>
                </div>
              </div>
              {% endfor %}
            </div>
          </li>
          {% endfor %}
        </ul>
      </div>
      {% else %}
      <p class="empty">无成员级变更</p>
      {% endfor %}

    </section>

    <section id="tab-added">
      {% for namespace, entries in grouped_added %}
      <div class="namespace-group">
        <h2>{{ namespace or '(全局)' }}</h2>
        <ul class="entry-list">
          {% for entry in entries %}
          <li class="entry" data-search="{{ namespace }} {{ entry.link }} {{ entry.path }} {{ entry.title }}">
            <div class="entry-header">
              <div>
                <span class="class-name">{{ entry.title }}</span>
                <a href="{{ doc_url(diff.to_version, entry.link) }}" target="_blank">{{ entry.link }}</a>
                <div class="path">{{ entry.path }}</div>
              </div>
              <span class="badge added">新增</span>
            </div>
          </li>
          {% endfor %}
        </ul>
      </div>
      {% endfor %}
    </section>

    <section id="tab-removed">
      {% for namespace, entries in grouped_removed %}
      <div class="namespace-group">
        <h2>{{ namespace or '(全局)' }}</h2>
        <ul class="entry-list">
          {% for entry in entries %}
          <li class="entry" data-search="{{ namespace }} {{ entry.link }} {{ entry.path }} {{ entry.title }}">
            <div class="entry-header">
              <div>
                <span class="class-name">{{ entry.title }}</span>
                <a href="{{ doc_url(diff.from_version, entry.link) }}" target="_blank">{{ entry.link }}</a>
                <div class="path">{{ entry.path }}</div>
              </div>
              <span class="badge removed">移除</span>
            </div>
          </li>
          {% endfor %}
        </ul>
      </div>
      {% endfor %}
    </section>

    <section id="tab-changed">
      {% for namespace, type_diffs in grouped_changed %}
      <div class="namespace-group">
        <h2>{{ namespace or '(全局)' }}</h2>
        <ul class="entry-list">
          {% for td in type_diffs %}
          <li class="entry" data-search="{{ namespace }} {{ td.type_link }} {{ td.type_title }}">
            <div class="entry-header">
              <div>
                <span class="class-name">{{ td.type_title }}</span>
                <a href="{{ doc_url(diff.to_version, td.type_link) }}" target="_blank">{{ td.type_link }}</a>
              </div>
              <span class="badge changed">变更</span>
            </div>
            <div class="member-block">
              {% if td.added_members %}
              <div class="member-group">
                <h4>新增成员 ({{ td.added_members|length }})</h4>
                <ul>
                  {% for mi in td.added_members %}
                  <li class="member-item">
                    <a href="{{ doc_url(diff.to_version, mi.member_link) }}" target="_blank">{{ mi.name }}</a>
                    {% if mi.signatures %}
                    <div class="sig-box new">{{ mi.signatures|join('\\n') }}</div>
                    {% endif %}
                  </li>
                  {% endfor %}
                </ul>
              </div>
              {% endif %}
              {% if td.removed_members %}
              <div class="member-group">
                <h4>移除成员 ({{ td.removed_members|length }})</h4>
                <ul>
                  {% for mi in td.removed_members %}
                  <li class="member-item">
                    <a href="{{ doc_url(diff.from_version, mi.member_link) }}" target="_blank">{{ mi.name }}</a>
                    {% if mi.signatures %}
                    <div class="sig-box old">{{ mi.signatures|join('\\n') }}</div>
                    {% endif %}
                  </li>
                  {% endfor %}
                </ul>
              </div>
              {% endif %}
              {% for mc in td.changed_members %}
              <div class="member-group">
                <h4>签名变更: <a href="{{ doc_url(diff.to_version, mc.member_link) }}" target="_blank">{{ mc.member_name }}</a></h4>
                <div class="sig-compare">
                  <div>
                    <div class="path">{{ diff.from_version }}</div>
                    <div class="sig-box old">{{ mc.old_signatures|join('\\n') or '(无签名)' }}</div>
                  </div>
                  <div>
                    <div class="path">{{ diff.to_version }}</div>
                    <div class="sig-box new">{{ mc.new_signatures|join('\\n') or '(无签名)' }}</div>
                  </div>
                </div>
              </div>
              {% endfor %}
            </div>
          </li>
          {% endfor %}
        </ul>
      </div>
      {% endfor %}
    </section>
  </main>

  <footer>
  由 UnityScriptingApiDiff 生成 · 基于 Unity 官方文档 toc.js 与 ScriptReference 页面解析
  </footer>

  <script>
    const searchInput = document.getElementById('search');
    const tabs = document.querySelectorAll('.tabs button');
    const sections = document.querySelectorAll('main > section');

    function applyFilter() {
      const q = searchInput.value.trim().toLowerCase();
      document.querySelectorAll('.entry').forEach(el => {
        const text = (el.dataset.search || el.textContent || '').toLowerCase();
        el.style.display = !q || text.includes(q) ? '' : 'none';
      });
    }

    searchInput.addEventListener('input', applyFilter);

    tabs.forEach(btn => {
      btn.addEventListener('click', () => {
        tabs.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        sections.forEach(s => s.classList.remove('active'));
        const target = tab === 'all' ? 'tab-all' : 'tab-' + tab;
        document.getElementById(target)?.classList.add('active');
      });
    });
  </script>
</body>
</html>"""
)


def write_html_report(
    diff: ApiDiff,
    output: Path | str,
) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = REPORT_TEMPLATE.render(
        diff=diff,
        summary=diff.summary,
        grouped_added=group_entries_by_namespace(diff.added),
        grouped_removed=group_entries_by_namespace(diff.removed),
        grouped_changed=group_member_diffs_by_namespace(diff.changed_types),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        doc_url=doc_url,
    )
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _entry_to_dict(entry) -> dict:
    namespace, class_name = split_namespace_class(entry.link)
    return {
        "link": entry.link,
        "namespace": namespace,
        "class_name": class_name,
        "path": entry.path,
        "title": entry.title,
    }


def write_json_report(diff: ApiDiff, output: Path | str) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "from_version": diff.from_version,
        "to_version": diff.to_version,
        "summary": diff.summary,
        "added": [_entry_to_dict(e) for e in diff.added],
        "removed": [_entry_to_dict(e) for e in diff.removed],
        "added_by_namespace": {
            namespace or "(global)": [_entry_to_dict(e) for e in entries]
            for namespace, entries in group_entries_by_namespace(diff.added)
        },
        "removed_by_namespace": {
            namespace or "(global)": [_entry_to_dict(e) for e in entries]
            for namespace, entries in group_entries_by_namespace(diff.removed)
        },
        "member_diffs": [
            {
                "type_link": td.type_link,
                "namespace": td.namespace,
                "class_name": td.type_title,
                "added_members": [
                    {
                        "member": mi.name,
                        "member_link": mi.member_link,
                        "signatures": mi.signatures,
                    }
                    for mi in td.added_members
                ],
                "removed_members": [
                    {
                        "member": mi.name,
                        "member_link": mi.member_link,
                        "signatures": mi.signatures,
                    }
                    for mi in td.removed_members
                ],
                "changed_members": [
                    {
                        "member": mc.member_name,
                        "member_link": mc.member_link,
                        "old_signatures": mc.old_signatures,
                        "new_signatures": mc.new_signatures,
                    }
                    for mc in td.changed_members
                ],
            }
            for td in diff.changed_types
        ],
        "member_diffs_by_namespace": {
            namespace or "(global)": [
                {
                    "type_link": td.type_link,
                    "class_name": td.type_title,
                    "added_members": [
                        {
                            "member": mi.name,
                            "member_link": mi.member_link,
                            "signatures": mi.signatures,
                        }
                        for mi in td.added_members
                    ],
                    "removed_members": [
                        {
                            "member": mi.name,
                            "member_link": mi.member_link,
                            "signatures": mi.signatures,
                        }
                        for mi in td.removed_members
                    ],
                    "changed_members": [
                        {
                            "member": mc.member_name,
                            "member_link": mc.member_link,
                            "old_signatures": mc.old_signatures,
                            "new_signatures": mc.new_signatures,
                        }
                        for mc in td.changed_members
                    ],
                }
                for td in type_diffs
            ]
            for namespace, type_diffs in group_member_diffs_by_namespace(diff.changed_types)
        },
    }

    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path
