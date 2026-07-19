import { useProjectSelection } from "@/contexts/project-selection";
import { StatusBadge } from "@/components/helios/primitives";

export function ProjectSelector() {
  const { projects, selectedProject, selectProject, loading, error, errorStatus, reload } =
    useProjectSelection();

  if (loading) {
    return (
      <div className="border-b border-rule px-4 py-3" aria-busy="true">
        <div className="label-eyebrow">Project</div>
        <p className="mt-1 font-mono text-[12px] text-muted-foreground">Loading projects…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="border-b border-rule px-4 py-3" role="alert">
        <div className="label-eyebrow">Project</div>
        <p className="mt-1 text-[12px] text-muted-foreground leading-snug">
          {errorStatus === 403 ? "You do not have access to this organization or project." : error}
        </p>
        <button
          type="button"
          onClick={() => reload()}
          className="mt-2 label-eyebrow border border-rule px-2 py-1 hover:bg-paper-2"
        >
          Retry
        </button>
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="border-b border-rule px-4 py-3">
        <div className="label-eyebrow">Project</div>
        <p className="mt-1 text-[12px] text-muted-foreground leading-snug">
          No projects in this organization. An administrator must link or create a project.
        </p>
      </div>
    );
  }

  return (
    <div className="border-b border-rule px-4 py-3">
      <label htmlFor="helios-project-select" className="label-eyebrow">
        Project
      </label>
      <div className="mt-1.5 flex items-center gap-2">
        <select
          id="helios-project-select"
          value={selectedProject?.id ?? ""}
          onChange={(event) => selectProject(event.target.value)}
          className="min-w-0 flex-1 border border-rule bg-paper px-2 py-1.5 font-mono text-[12px] outline-none focus:border-ink"
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name || project.slug}
            </option>
          ))}
        </select>
        {selectedProject ? (
          <StatusBadge tone="neutral">{selectedProject.environment}</StatusBadge>
        ) : null}
      </div>
      {selectedProject ? (
        <p
          className="mt-1.5 font-mono text-[11px] text-muted-foreground truncate"
          title={selectedProject.slug}
        >
          {selectedProject.slug}
        </p>
      ) : null}
    </div>
  );
}
