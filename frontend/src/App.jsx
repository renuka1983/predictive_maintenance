import { Navigate, Route, Routes } from 'react-router-dom';
import FeatureGate from './components/FeatureGate';
import Navigation from './components/Navigation';
import { Loading } from './components/States';
import { useTenant } from './hooks/useTenant';

import Benchmark from './pages/Benchmark';
import FleetComparison from './pages/FleetComparison';
import Dashboard from './pages/Dashboard';
import ImpactSimulator from './pages/ImpactSimulator';
import Machines from './pages/Machines';
import Maintenance from './pages/Maintenance';
import Monitoring from './pages/Monitoring';
import NotFound from './pages/NotFound';
import ProductionLines from './pages/ProductionLines';
import Reliability from './pages/Reliability';
import RiskAnalysis from './pages/RiskAnalysis';
import Portfolio from './pages/Portfolio';
import Settings from './pages/Settings';
import Sites from './pages/Sites';
import Telemetry from './pages/Telemetry';

export default function App() {
  const { loading, error, tenantId, tenants } = useTenant();

  if (loading) {
    return (
      <div className="state">
        <Loading label="Connecting to the platform…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="state error">
        <h1>Cannot reach the API</h1>
        <p>{error.message}</p>
        <p className="muted small">
          Check that the backend is running and VITE_API_BASE_URL points at it.
        </p>
      </div>
    );
  }

  if (!tenants.length) {
    return (
      <div className="state">
        <h1>No tenants yet</h1>
        <p className="muted small">
          Create one with POST /api/v1/tenants, or load the pilot data with
          <code> python -m ml.data_generation.load_to_db --reset</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="app">
      <Navigation />
      <main className="main">
        {!tenantId ? (
          <Loading />
        ) : (
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/machines" element={<Machines />} />
            <Route path="/maintenance" element={<Maintenance />} />
            <Route path="/reliability" element={<Reliability />} />
            <Route
              path="/production"
              element={
                <FeatureGate
                  feature="production_tracking"
                  requirements={['Import production batches from your MES or ERP']}
                >
                  <ProductionLines />
                </FeatureGate>
              }
            />
            <Route
              path="/risk"
              element={
                <FeatureGate
                  feature="failure_risk_scoring"
                  requirements={[
                    'Import production batches so the model can learn from quality and throughput',
                  ]}
                >
                  <RiskAnalysis />
                </FeatureGate>
              }
            />
            <Route
              path="/simulator"
              element={
                <FeatureGate
                  feature="impact_simulator"
                  requirements={['Import production data and set machine line positions']}
                >
                  <ImpactSimulator />
                </FeatureGate>
              }
            />
            <Route
              path="/monitoring"
              element={
                <FeatureGate
                  feature="realtime_monitoring"
                  requirements={['Stream IoT sensor readings from instrumented machines']}
                >
                  <Monitoring />
                </FeatureGate>
              }
            />
            <Route
              path="/telemetry"
              element={
                <FeatureGate
                  feature="sensor_telemetry"
                  requirements={['Stream IoT sensor readings from instrumented machines']}
                >
                  <Telemetry />
                </FeatureGate>
              }
            />
            <Route
              path="/portfolio"
              element={
                <FeatureGate
                  feature="multi_site"
                  requirements={['Onboard a second site and set the site field on its machines']}
                >
                  <Portfolio />
                </FeatureGate>
              }
            />
            <Route
              path="/fleet"
              element={
                <FeatureGate
                  feature="fleet_comparison"
                  requirements={[
                    'Onboard a second site',
                    'Set machine_type on machines so asset classes can be compared',
                  ]}
                >
                  <FleetComparison />
                </FeatureGate>
              }
            />
            <Route
              path="/sites"
              element={
                <FeatureGate
                  feature="site_registry"
                  requirements={['Onboard a second site to unlock the enterprise tier']}
                >
                  <Sites />
                </FeatureGate>
              }
            />
            <Route
              path="/benchmark"
              element={
                <FeatureGate
                  feature="benchmarking"
                  requirements={['Onboard a second site and set the site field on its machines']}
                >
                  <Benchmark />
                </FeatureGate>
              }
            />
            <Route path="/settings" element={<Settings />} />
            <Route path="/404" element={<NotFound />} />
            <Route path="*" element={<Navigate to="/404" replace />} />
          </Routes>
        )}
      </main>
    </div>
  );
}
