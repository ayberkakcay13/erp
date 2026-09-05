import { Component } from 'react';

/**
 * Beklenmedik bir render hatasinda uygulamanin bos beyaz ekrana dusmesini engeller.
 */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('Beklenmeyen hata:', error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div data-testid="app-crash" className="p-8">
        <h2 className="text-lg font-semibold text-red-700 mb-2">Bir seyler ters gitti</h2>
        <p className="text-sm text-gray-600 mb-4">
          Beklenmeyen bir hata olustu. Sayfayi yenilemeyi deneyebilirsin.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="px-3 py-1.5 rounded text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700"
        >
          Sayfayi yenile
        </button>
      </div>
    );
  }
}
