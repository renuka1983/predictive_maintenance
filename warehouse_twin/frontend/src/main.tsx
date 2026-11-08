import { createRoot } from 'react-dom/client';
import { CssBaseline, ThemeProvider } from '@mui/material';
import App from './App';
import { theme } from './theme';
import { connect } from './store';

connect();
createRoot(document.getElementById('root')!).render(
  <>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </>,
);
