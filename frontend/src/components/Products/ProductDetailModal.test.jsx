import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ProductDetailModal from './ProductDetailModal';
import { productAPI } from '../../services/api';

jest.mock('../../services/api', () => ({
  productAPI: {
    orders: jest.fn(),
    salesTrend: jest.fn(),
  },
}));

const ORDERS = [
  { id: '#S201', customer: 'Acme Corp', order_date: '2026-09-10', delivery_date: '2026-09-15', amount: 7499, status: 'pending' },
  { id: '#S196', customer: 'TechStartup', order_date: '2026-09-04', delivery_date: '2026-09-09', amount: 7499, status: 'processing' },
  { id: '#S188', customer: 'Mehmet Demir', order_date: '2026-08-27', delivery_date: '2026-09-01', amount: 7499, status: 'delivered' },
];

const PRODUCT = { id: 17, name: 'Monitor', sku: 'MON-001' };

beforeEach(() => {
  productAPI.orders.mockResolvedValue(ORDERS);
  productAPI.salesTrend.mockResolvedValue([]);
});

describe('ProductDetailModal', () => {
  test('baslikta urun adini ve SKU\'yu gosterir', async () => {
    render(<ProductDetailModal product={PRODUCT} onClose={() => {}} />);
    expect(screen.getByText('Monitor')).toBeInTheDocument();
    expect(screen.getByText('MON-001')).toBeInTheDocument();
    await waitFor(() => expect(productAPI.orders).toHaveBeenCalledWith(17));
  });

  test('ikinci kolon Musteri baslikli ve Tab 1 yalnizca pending/processing gosterir', async () => {
    render(<ProductDetailModal product={PRODUCT} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('#S201')).toBeInTheDocument());
    expect(screen.getByText('Musteri')).toBeInTheDocument();
    expect(screen.getByText('#S196')).toBeInTheDocument();
    expect(screen.queryByText('#S188')).not.toBeInTheDocument();
  });

  test('Tab 2ye gecince tum durumlardan siparisler gosterilir', async () => {
    render(<ProductDetailModal product={PRODUCT} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText('#S201')).toBeInTheDocument());

    await userEvent.click(screen.getByTestId('tab-recent'));
    expect(screen.getByText('#S188')).toBeInTheDocument();
  });

  test('backdrop tiklamasi onClose cagirir', async () => {
    const onClose = jest.fn();
    render(<ProductDetailModal product={PRODUCT} onClose={onClose} />);
    await waitFor(() => expect(screen.getByText('Monitor')).toBeInTheDocument());
    await userEvent.click(screen.getByTestId('product-detail-modal'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
