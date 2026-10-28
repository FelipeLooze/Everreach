import { useState } from 'react';
import type { PlantAction, PlantObservation, SystemInventory } from '@/types/game';

const labels: Record<string, string> = {arvore: 'Árvore', arbusto: 'Arbusto', flor: 'Flor', erva: 'Erva', graminea: 'Gramínea', samambaia: 'Samambaia', musgo: 'Musgo', liquen: 'Líquen', fungo: 'Fungo'};
const reasons: Record<string, string> = {outside_catalog_season: 'Fora da estação de coleta', outside_catalog_day_period: 'Indisponível neste horário', seasonal_biological_activity_not_supported: 'Sem atividade biológica suficiente nesta estação', outside_L1_maturity_or_phenology: 'Parte ainda não madura ou fora da fase de produção', depleted_or_waiting_for_L1_growth: 'Estoque esgotado; recuperação depende do ciclo vegetal', individual_removed: 'Indivíduo removido'};

export function VegetationNearby({ plants, inventory, busy, onAction }: {
  plants: PlantObservation[]; inventory: SystemInventory; busy: boolean;
  onAction: (text: string, technique?: string, action?: PlantAction) => Promise<void>;
}) {
  const tools = inventory.items.filter(item => item.name === 'Tesoura de campo');
  const [tool, setTool] = useState('');
  const [quantity, setQuantity] = useState(1);
  return <section className="vegetation-nearby" aria-label="Vegetação próxima">
    <button disabled={busy} onClick={() => void onAction('Observo a vegetação ao meu redor.', undefined, {kind: 'look'})}>Observar vegetação</button>
    {plants.length > 0 && <>
      <p>Escolha uma planta próxima. Nomes dependem do seu conhecimento. A coleta exige instrução, ferramenta e partes disponíveis.</p>
      <label>Ferramenta <select value={tool || tools[0]?.item_instance_id || ''} onChange={event => setTool(event.target.value)}>
        {tools.map(item => <option key={item.item_instance_id} value={item.item_instance_id}>{item.name}</option>)}
        {!tools.length && <option value="">Nenhuma tesoura de campo acessível</option>}
      </select></label>
      <label>Quantidade <input type="number" min={1} max={10000} value={quantity} onChange={event => setQuantity(Math.max(1, Number(event.target.value) || 1))} /></label>
    </>}
    {plants.map((plant, index) => <article key={plant.individual_id}>
      <h4>{plant.name || `${labels[plant.kind] || 'Planta'} desconhecida ${index + 1}`}</h4>
      <p>Altura: {(plant.height_cm / 100).toFixed(2)} m · {plant.alive ? (plant.maturity === 'adult' ? 'Adulta' : 'Em desenvolvimento') : 'Removida'}</p>
      <button disabled={busy} onClick={() => void onAction('Examino esta planta.', undefined, {kind: 'observe', individual_id: plant.individual_id})}>Examinar</button>
      {plant.parts.map(part => <div key={part.part_id}>
        <span>{part.part.replaceAll('_', ' ')}: {part.remaining} unidade(s){part.unit_mass_mg ? ` · ${(part.unit_mass_mg / 1000).toLocaleString('pt-BR')} g/unidade` : ''}</span>{' '}
        <button disabled={busy || !part.available_now || !tools.length || quantity > part.remaining || quantity > (part.per_action_max || 1)}
          onClick={() => void onAction(`Coleto ${quantity} unidade(s) de ${part.part}.`, undefined, {
            kind: 'harvest', individual_id: plant.individual_id, part_id: part.part_id, quantity,
            tool_instance_id: tool || tools[0]?.item_instance_id,
          })}>Coletar {part.part.replaceAll('_', ' ')}</button>
        {!part.available_now && <small> {reasons[part.reason || ''] || 'Coleta indisponível pelas condições atuais.'}</small>}
      </div>)}
      <button disabled={busy || !tools.length} onClick={() => {
        if (window.confirm('Tentar retirar este indivíduo? A ação é destrutiva e exige ferramenta e proficiência adequadas.'))
          void onAction('Tento retirar esta planta.', undefined, {kind: 'remove', individual_id: plant.individual_id, tool_instance_id: tool || tools[0]?.item_instance_id});
      }}>Tentar retirar planta</button>
    </article>)}
  </section>;
}
