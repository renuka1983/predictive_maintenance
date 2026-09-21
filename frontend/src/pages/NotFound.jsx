import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="state">
      <h1>Page not found</h1>
      <p>
        <Link to="/" style={{ color: 'var(--series-1)' }}>
          Back to the dashboard
        </Link>
      </p>
    </div>
  );
}
