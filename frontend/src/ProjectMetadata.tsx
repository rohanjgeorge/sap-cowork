import { useId } from "react";

export type Metadata = {
  organization_id?: string | null;
  program_id?: string | null;
  sap_applicability?: Record<string, string>;
};
const sapFields = [
  [
    "product",
    "SAP product",
    "Target SAP application, e.g. SAP S/4HANA or SAP ECC. Used to match product-specific guidance.",
  ],
  [
    "deployment",
    "Deployment model",
    "How SAP is deployed: on-premise, private cloud or public cloud. Used to match deployment-specific guidance.",
  ],
  [
    "release",
    "SAP release/version",
    "Target software version, e.g. 2023 FPS02. Used to check whether tagged evidence applies to your release.",
  ],
  [
    "system",
    "SAP system",
    "Target SAP system ID, e.g. DEV or QAS. Used to match evidence for that specific system.",
  ],
  [
    "client",
    "SAP client",
    "Logical client within the SAP system, e.g. 100. Used to match client-specific evidence.",
  ],
];
export default function ProjectMetadata({
  value,
  onChange,
}: {
  value: Metadata;
  onChange: (value: Metadata) => void;
}) {
  const id = useId();
  return (
    <details className="project-metadata">
      <summary>Optional project metadata</summary>
      {[
        [
          "organization_id",
          "Organization ID",
          "Company or customer identifier, e.g. ACME. Used to match context tagged for the same organization.",
        ],
        [
          "program_id",
          "Program ID",
          "Business initiative identifier, e.g. S4-TRANSFORMATION. Used to match context tagged for the same program.",
        ],
      ].map(([key, label, note]) => (
        <div className="metadata-field" key={key}>
          <label>
            {label}
            <input
              aria-describedby={`${id}-${key}-note`}
              value={(value[key as keyof Metadata] as string) || ""}
              onChange={(e) =>
                onChange({ ...value, [key]: e.target.value || null })
              }
            />
          </label>
          <small id={`${id}-${key}-note`}>{note}</small>
        </div>
      ))}
      {sapFields.map(([key, label, note]) => (
        <div className="metadata-field" key={key}>
          <label>
            {label}
            <input
              aria-describedby={`${id}-${key}-note`}
              value={value.sap_applicability?.[key] || ""}
              onChange={(e) => {
                const sap = { ...value.sap_applicability };
                if (e.target.value) sap[key] = e.target.value;
                else delete sap[key];
                onChange({ ...value, sap_applicability: sap });
              }}
            />
          </label>
          <small id={`${id}-${key}-note`}>{note}</small>
        </div>
      ))}
    </details>
  );
}
