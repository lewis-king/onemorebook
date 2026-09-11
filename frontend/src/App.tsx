import { Router, Route, Navigate } from "@solidjs/router";
// import Navbar from "./components/Navbar";
import HomePage from "./pages/HomePage";
import BookPage from "./pages/BookPage";

function App() {
  return (
    <div class="min-h-screen bg-dragons-pattern bg-cover bg-fixed bg-center">
        <div class="min-h-screen bg-white/80 backdrop-blur-sm">
          
          <main class="container mx-auto px-4 py-8">
    <Router>
      
              <Route path="/" component={HomePage} />
              <Route path="/create" component={() => <Navigate href="/" />} />
              <Route path="/book/:id" component={BookPage} />
              <Route path="/book/upload" component={() => <Navigate href="/" />} />
              <Route path="/book/:id/upload" component={() => <Navigate href="/" />} />
          
    </Router>
            </main>
        </div>
      </div>
  );
}

export default App;
