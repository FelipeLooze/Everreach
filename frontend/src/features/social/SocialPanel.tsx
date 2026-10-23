import { useEffect, useState } from "react";
import { getSocialState } from "@/api/social";
import type { SocialState } from "@/types/game";
import { organizationReputationLabel, organizationTypeLabel } from "@/utils/labels";

const RELATION_LABELS: Record<string, string> = {
  ALLIED: "Aliada",
  FRIENDLY: "Amistosa",
  NEUTRAL: "Neutra",
  RIVAL: "Rival",
  HOSTILE: "Hostil",
  AT_WAR: "Em guerra",
  TRADE_PARTNER: "Parceira comercial",
};

export function SocialPanel({ campaignId, characterId }: { campaignId: string; characterId: string }) {
  const [social, setSocial] = useState<SocialState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getSocialState(campaignId, characterId)
      .then((response) => {
        if (active) setSocial(response);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Falha ao carregar o estado social.");
      });
    return () => {
      active = false;
    };
  }, [campaignId, characterId]);

  if (error) return <p className="panel-error">{error}</p>;
  if (!social) return <p>Carregando…</p>;

  return (
    <div className="social-panel">
      <section>
        <h3>Grupo atual</h3>
        {social.active_group ? (
          <article className="social-card">
            <h4>{social.active_group.name ?? organizationTypeLabel(social.active_group.group_type)}</h4>
            {social.active_group.purpose && <p>{social.active_group.purpose}</p>}
            <ul>
              {social.active_group.members.map((member) => (
                <li key={`${member.actor_type}:${member.actor_id}`}>
                  {member.name}{member.leader ? " — líder" : ""}
                </li>
              ))}
            </ul>
          </article>
        ) : (
          <p className="panel-empty">Você não faz parte de um grupo no momento.</p>
        )}
      </section>

      <section>
        <h3>Organizações conhecidas</h3>
        {social.organizations.length === 0 ? (
          <p className="panel-empty">Nenhuma organização conhecida neste momento.</p>
        ) : (
          <div className="social-list">
            {social.organizations.map((organization) => (
              <article className="social-card" key={organization.id}>
                <div className="social-card-heading">
                  <h4>{organization.name}</h4>
                  <span>{organizationTypeLabel(organization.organization_type)}</span>
                </div>
                {organization.description && <p>{organization.description}</p>}
                <dl>
                  <div><dt>Sede</dt><dd>{organization.headquarters_name ?? "Desconhecida"}</dd></div>
                  <div>
                    <dt>Liderança</dt>
                    <dd>
                      {organization.leader_name
                        ? `${organization.leader_name}${organization.leader_title ? ` (${organization.leader_title})` : ""}`
                        : "Desconhecida"}
                    </dd>
                  </div>
                  <div><dt>Reputação</dt><dd>{organizationReputationLabel(organization.reputation)}</dd></div>
                  <div>
                    <dt>Vínculo</dt>
                    <dd>{organization.membership === "MEMBER" ? organization.role ?? "Membro" : "Não membro"}</dd>
                  </div>
                  <div><dt>Avisos ativos</dt><dd>{organization.active_notices}</dd></div>
                  {organization.origin === "TRANSPORTED_CREATED" && (
                    <div>
                      <dt>Situação</dt>
                      <dd>{organization.formality === "FORMALLY_RECOGNIZED" ? "Registrada" : "Informal"}</dd>
                    </div>
                  )}
                  {organization.goal && (
                    <div>
                      <dt>Objetivo</dt>
                      <dd>
                        {organization.goal.description} ({organization.goal.progress}/{organization.goal.target})
                        {organization.goals_achieved > 0 && ` — ${organization.goals_achieved} já alcançado(s)`}
                      </dd>
                    </div>
                  )}
                  {organization.relations.length > 0 && (
                    <div>
                      <dt>Relações</dt>
                      <dd>
                        {organization.relations
                          .map((relation) => `${RELATION_LABELS[relation.relation_type] ?? relation.relation_type} de ${relation.organization_name}`)
                          .join("; ")}
                      </dd>
                    </div>
                  )}
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
