import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TabView from './TabView';

const TABS = [
  { key: 'ongoing', label: 'Devam Eden' },
  { key: 'recent', label: 'Son Siparisler' },
];

describe('TabView', () => {
  test('aktif sekme dogru sekilde isaretlenir', () => {
    render(
      <TabView tabs={TABS} active="ongoing" onChange={() => {}}>
        <p>Icerik</p>
      </TabView>
    );
    expect(screen.getByTestId('tab-ongoing')).toHaveClass('border-indigo-600');
    expect(screen.getByTestId('tab-recent')).not.toHaveClass('border-indigo-600');
  });

  test('sekmeye tiklama onChange\'i dogru key ile cagirir', async () => {
    const onChange = jest.fn();
    render(
      <TabView tabs={TABS} active="ongoing" onChange={onChange}>
        <p>Icerik</p>
      </TabView>
    );
    await userEvent.click(screen.getByTestId('tab-recent'));
    expect(onChange).toHaveBeenCalledWith('recent');
  });
});
