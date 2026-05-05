import type { RoleTab } from "../../stores/orchStore";

const ROLES: { key: RoleTab; label: string }[] = [
  { key: "req_decomposer", label: "REQ拆分" },
  { key: "req_completeness_critic", label: "REQ校验" },
  { key: "arch_designer", label: "ARCH设计" },
  { key: "arch_coverage_critic", label: "ARCH校验" },
];

export interface RolesTabBarProps {
  active: RoleTab;
  onChange: (r: RoleTab) => void;
}

export function RolesTabBar({ active, onChange }: RolesTabBarProps) {
  return (
    <div style={{ display: "flex", borderBottom: "1px solid #ddd", gap: 4 }}>
      {ROLES.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          aria-current={active === key ? "true" : undefined}
          style={{
            padding: "8px 10px",
            border: "none",
            borderBottom:
              active === key ? "2px solid #1976d2" : "2px solid transparent",
            background: active === key ? "#e3f2fd" : "#f5f5f5",
            fontWeight: active === key ? 600 : 400,
          }}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
      <span style={{ flex: 1 }} />
      <button type="button" disabled title="二期扩展角色" aria-label="+">
        +
      </button>
    </div>
  );
}
