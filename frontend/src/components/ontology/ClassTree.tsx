import { ChevronDown, ChevronRight, Circle } from "lucide-react";
import { useMemo, useState } from "react";
import type { OntologyClass } from "../../types";
import { humanize } from "../../utils/format";

interface TreeNode {
  cls: OntologyClass;
  children: TreeNode[];
}

export function buildTree(classes: OntologyClass[]): TreeNode[] {
  const byId = new Map(classes.map((c) => [c.id, c]));
  const build = (c: OntologyClass, seen: Set<string>): TreeNode => ({
    cls: c,
    children: c.children
      .map((ch) => byId.get(ch.id))
      .filter((x): x is OntologyClass => Boolean(x) && !seen.has(x!.id))
      .map((x) => build(x, new Set([...seen, x.id]))),
  });
  return classes
    .filter((c) => c.parents.filter((p) => byId.has(p.id)).length === 0)
    .map((c) => build(c, new Set([c.id])));
}

function matches(node: TreeNode, q: string): boolean {
  return node.cls.id.toLowerCase().includes(q) || node.children.some((c) => matches(c, q));
}

function Node({
  node,
  depth,
  selected,
  onSelect,
  expanded,
  toggle,
  query,
}: {
  node: TreeNode;
  depth: number;
  selected: string | null;
  onSelect: (id: string) => void;
  expanded: Set<string>;
  toggle: (id: string) => void;
  query: string;
}) {
  if (query && !matches(node, query)) return null;
  const open = query ? true : expanded.has(node.cls.id);
  const hasChildren = node.children.length > 0;
  return (
    <li>
      <div
        className={`tree-row ${selected === node.cls.id ? "selected" : ""}`}
        style={{ paddingLeft: 8 + depth * 16 }}
        onClick={() => onSelect(node.cls.id)}
        role="treeitem"
        aria-expanded={hasChildren ? open : undefined}
        aria-selected={selected === node.cls.id}
      >
        {hasChildren ? (
          <button
            className="tree-toggle"
            onClick={(e) => {
              e.stopPropagation();
              toggle(node.cls.id);
            }}
            aria-label={open ? "Replier" : "Déplier"}
          >
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : (
          <span className="tree-leaf">
            <Circle size={6} />
          </span>
        )}
        <span className="tree-label">{humanize(node.cls.id)}</span>
        {node.cls.total_instances > 0 && <span className="tree-count">{node.cls.total_instances}</span>}
      </div>
      {hasChildren && open && (
        <ul>
          {node.children.map((c) => (
            <Node key={c.cls.id} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} expanded={expanded} toggle={toggle} query={query} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ClassTree({
  classes,
  selected,
  onSelect,
  filter,
}: {
  classes: OntologyClass[];
  selected: string | null;
  onSelect: (id: string) => void;
  filter: string;
}) {
  const tree = useMemo(() => buildTree(classes), [classes]);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(tree.map((t) => t.cls.id)));
  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const expandAll = () => setExpanded(new Set(classes.map((c) => c.id)));
  const collapseAll = () => setExpanded(new Set());

  return (
    <div className="class-tree">
      <div className="tree-actions">
        <button className="link-btn" onClick={expandAll}>
          Tout déplier
        </button>
        <button className="link-btn" onClick={collapseAll}>
          Tout replier
        </button>
      </div>
      <ul role="tree">
        {tree.map((n) => (
          <Node key={n.cls.id} node={n} depth={0} selected={selected} onSelect={onSelect} expanded={expanded} toggle={toggle} query={filter.toLowerCase()} />
        ))}
      </ul>
    </div>
  );
}
