import { createSignal } from "solid-js";
import { useNavigate } from "@solidjs/router";
import { bookService } from "../services/api";
import type { CreateBookParams } from "../types/book";

export default function CreateStoryPage() {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = createSignal(false);
  const [formData, setFormData] = createSignal<CreateBookParams>({
    characters: [],
    storyPrompt: "",
    ageRange: "4-5"
  });
  const [charactersInput, setCharactersInput] = createSignal("");

  const handleCharactersBlur = () => {
    setFormData({
      ...formData(),
      characters: charactersInput().split(',').map(c => c.trim()).filter(Boolean)
    });
  };

  const handleSubmit = async (e: Event) => {
    e.preventDefault();
    setFormData({
      ...formData(),
      characters: charactersInput().split(',').map(c => c.trim()).filter(Boolean)
    });
    setIsLoading(true);

    try {
      const result = await bookService.createBook(formData());
      if (result.bookId) {
        navigate(`/book/${result.bookId}`);
      } else {
        console.error('No bookId returned from API:', result);
      }
    } catch (error) {
      console.error('Failed to create story:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
      <div class="max-w-2xl mx-auto">
        <h1 class="text-4xl font-comic text-center text-kiddy-primary mb-8">
          Create Your Magical Story
        </h1>
        <form onSubmit={handleSubmit} class="space-y-6 bg-white p-8 rounded-lg shadow-lg">
          <div>
            <label class="block text-gray-700 mb-2" for="characters">
              Who are the characters in your story?
            </label>
            <input
                id="characters"
                type="text"
                class="w-full p-3 border rounded-lg focus:ring-2 focus:ring-kiddy-primary"
                placeholder="E.g. brave dragon, wise owl"
                value={charactersInput()}
                onInput={(e) => setCharactersInput(e.currentTarget.value)}
                onBlur={handleCharactersBlur}
            />
          </div>

          <div>
            <label class="block text-gray-700 mb-2" for="storyPrompt">
              What is the story about in one or two sentences?
            </label>
            <input
                id="storyPrompt"
                type="text"
                class="w-full p-3 border rounded-lg focus:ring-2 focus:ring-kiddy-primary"
                placeholder="E.g. A magical journey through the forest to find a lost friend."
                value={formData().storyPrompt}
                onInput={(e) => setFormData({
                  ...formData(),
                  storyPrompt: e.currentTarget.value
                })}
            />
          </div>

          <div>
            <label class="block text-gray-700 mb-2" for="ageRange">
              Age Range
            </label>
              <select
                  id="ageRange"
                  class="w-full p-3 border rounded-lg focus:ring-2 focus:ring-kiddy-primary"
                  value={formData().ageRange}
                  onChange={(e) => setFormData({
                      ...formData(),
                      ageRange: e.currentTarget.value
                  })}
              >
                  <option value="1-2">1-2 years</option>
                  <option value="2-3">2-3 years</option>
                  <option value="4-5">4-5 years</option>
                  <option value="5-6">5-6 years</option>
                  <option value="7-8">7-8 years</option>
              </select>
          </div>

            <button
                type="submit"
              class="btn-primary w-full disabled:opacity-50"
              disabled={isLoading()}
          >
            {isLoading() ? 'Creating Story...' : 'Create My Story! 🌟'}
          </button>
        </form>
      </div>
  );
}