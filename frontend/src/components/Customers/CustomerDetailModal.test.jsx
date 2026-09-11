import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CustomerDetailModal from './CustomerDetailModal';
import { customerAPI } from '../../services/api';

jest.mock('../../services/api', () => ({
  customerAPI: {
    orders: jest.fn(),
    salesTrend: jest.fn(),
  },
}));

const ORDERS = [
  { id: '#S101', product: 'Monitor', order_date: '2026-09-10', delivery_date: '2026-09-15', amount: 7499, status: 'pending' },
  { id: '#S096', product: 'Mouse', order_date: '2026-09-05', delivery_date: '2026-09-10', amount: 450, status: 'processing' },
  { id: '#S088', product: 'Klavye', order_date: '2026-08-28', delivery_date: '2026-09-02', amount: 1250, status: 'delivered' },
  { id: '#S080', product: 'Monitor', order_date: '2026-08-15', delivery_date: '2026-08-20', amount: 7499, status: 'delivered' },
];

const CUSTOMER = { id: 42, name: 'Acme Corp', email: 'acme@example.com' };

beforeEach(() => {
  customerAPI.orders.mockResolvedValue(ORDERS);
  customerAPI.salesTrend.mockResolvedValue([]);
});

describe('CustomerDetailModal', () => {
  test('baslikta musteri adini ve e-postasini gosterir', async () => {
    render(<CustomerDetailModal customer={CUSTOMER} onClose={() => {}} />);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('acme@example.com')).toBeInTheDocument();
    await waitFor(() => expect(customerAPI.orders).toHaveBeenCalledWith(42));
  });

  test('Tab 1 (Devam Eden) varsayilan acik ve yalnizca pending/processing satirlari gosterir', async () => {
    render(<CustomerDetailModal customer={CUSTOMER} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('#S101')).toBeInTheDocument());
    expect(screen.getByText('#S096')).toBeInTheDocument();
    expect(screen.queryByText('#S088')).not.toBeInTheDocument();
    expect(screen.queryByText('#S080')).not.toBeInTheDocument();
  });

  test('Tab 2ye gecince tum durumlardan en fazla 5 siparis gosterir', async () => {
    render(<CustomerDetailModal customer={CUSTOMER} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('#S101')).toBeInTheDocument());

    await userEvent.click(screen.getByTestId('tab-recent'));
    // Son siparisler tarihe gore azalan: hepsi 4 kayit, 5'ten az oldugu icin tumu gorunur
    expect(screen.getByText('#S101')).toBeInTheDocument();
    expect(screen.getByText('#S088')).toBeInTheDocument();
    expect(screen.getByText('#S080')).toBeInTheDocument();
  });

  test('X butonu onClose cagirir', async () => {
    const onClose = jest.fn();
    render(<CustomerDetailModal customer={CUSTOMER} onClose={onClose} />);
    await waitFor(() => expect(screen.getByText('#S101')).toBeInTheDocument());
    await userEvent.click(screen.getByTestId('modal-x'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test('siparis yoksa bos durum mesaji gosterir', async () => {
    customerAPI.orders.mockResolvedValue([]);
    render(<CustomerDetailModal customer={CUSTOMER} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('Devam eden siparis yok.')).toBeInTheDocument());
  });
});
