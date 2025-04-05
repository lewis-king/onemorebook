import { A } from "@solidjs/router";

export default function Navbar() {
  return (
    <nav class="bg-white shadow-lg">
      <div class="container mx-auto px-4">
        <div class="flex justify-between items-center h-16">
          <A href="/" class="flex items-center space-x-2">
            <span class="text-2xl font-comic text-kiddy-primary">OneMoreBook.ai</span>
          </A>
          <div class="flex space-x-4">
            <A href="/" class="text-gray-700 hover:text-kiddy-primary px-3 py-2 rounded-md">
              Stories
            </A>
            <A href="/create" class="bg-kiddy-primary text-white px-4 py-2 rounded-full hover:bg-opacity-90">
              Create Story
            </A>
          </div>
        </div>
      </div>
    </nav>
  );
}