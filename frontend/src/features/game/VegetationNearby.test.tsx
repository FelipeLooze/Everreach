import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VegetationNearby } from '@/features/game/VegetationNearby';
import type { PlantObservation, SystemInventory } from '@/types/game';

const plant: PlantObservation = {
  individual_id: 'vgi:confirmed-nearby', name: null, kind: 'graminea', height_cm: 74,
  maturity: 'adult', alive: true, identified: false,
  parts: [{part_id: 'EV-FL-0001-P01', part: 'fibras', remaining: 4, available_now: true,
    reason: null, unit_mass_mg: 2378, per_action_max: 2}],
};

const inventory = {
  items: [{item_instance_id: 'tool:confirmed', name: 'Tesoura de campo', type: 'TOOL', quantity: 1,
    quality: 'STANDARD', condition: 'EXCELLENT', material_name: null, equipped_slot: 'WAIST',
    accessibility: 'QUICK', contained_in_name: null}],
  total_weight: 1, carrying_capacity: 20, encumbrance: 'LIGHT',
} as unknown as SystemInventory;

describe('VegetationNearby', () => {
  afterEach(cleanup);

  it('observes via the backend action contract and keeps unknown plants unidentified', async () => {
    const onAction = vi.fn().mockResolvedValue(undefined);
    render(<VegetationNearby plants={[]} inventory={inventory} busy={false} onAction={onAction} />);
    fireEvent.click(screen.getByRole('button', {name: 'Observar vegetação'}));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith(
      'Observo a vegetação ao meu redor.', undefined, {kind: 'look'},
    ));

    cleanup();
    render(<VegetationNearby plants={[plant]} inventory={inventory} busy={false} onAction={onAction} />);
    expect(screen.getByRole('heading', {name: 'Gramínea desconhecida 1'})).toBeInTheDocument();
    expect(screen.queryByText('EV-FL-0001')).not.toBeInTheDocument();
  });

  it('submits only the observed individual, available part and actual carried tool', async () => {
    const onAction = vi.fn().mockResolvedValue(undefined);
    render(<VegetationNearby plants={[plant]} inventory={inventory} busy={false} onAction={onAction} />);
    fireEvent.click(screen.getByRole('button', {name: 'Coletar fibras'}));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith(
      'Coleto 1 unidade(s) de fibras.', undefined,
      {kind: 'harvest', individual_id: plant.individual_id, part_id: 'EV-FL-0001-P01',
        quantity: 1, tool_instance_id: 'tool:confirmed'},
    ));
  });
});
