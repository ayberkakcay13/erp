import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DetailModal from './DetailModal';

describe('DetailModal', () => {
  test('backdrop tiklamasi onClose cagirir', async () => {
    const onClose = jest.fn();
    render(
      <DetailModal title="Acme Corp" onClose={onClose} testid="test-modal">
        <p>Icerik</p>
      </DetailModal>
    );
    await userEvent.click(screen.getByTestId('test-modal'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test('panel icine tiklama onClose cagirmaz (stopPropagation)', async () => {
    const onClose = jest.fn();
    render(
      <DetailModal title="Acme Corp" onClose={onClose} testid="test-modal">
        <p>Icerik</p>
      </DetailModal>
    );
    await userEvent.click(screen.getByText('Icerik'));
    expect(onClose).not.toHaveBeenCalled();
  });

  test('X butonu ve Kapat butonu onClose cagirir', async () => {
    const onClose = jest.fn();
    render(
      <DetailModal title="Acme Corp" onClose={onClose} testid="test-modal">
        <p>Icerik</p>
      </DetailModal>
    );
    await userEvent.click(screen.getByTestId('modal-x'));
    expect(onClose).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByTestId('modal-close'));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  test('title ve subtitle render edilir', () => {
    render(
      <DetailModal title="Acme Corp" subtitle="acme@example.com" onClose={() => {}} testid="test-modal">
        <p>Icerik</p>
      </DetailModal>
    );
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('acme@example.com')).toBeInTheDocument();
  });
});
