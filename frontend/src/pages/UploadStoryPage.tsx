import { createSignal, Show, For, onMount, createEffect } from "solid-js";
import { useNavigate, useParams } from "@solidjs/router";
import { bookService } from "../services/api";

interface StoryPage {
  text: string;
  pageNumber: number;
  imagePrompt: string;
  imageUrl?: string;
  charactersPresent?: string[];
  isMainCharacterPresent?: boolean;
}

interface StoryMetadata {
  title: string;
  theme: string;
  bookSummary: string;
  mainCharacterDescriptivePrompt: string;
  coverImagePrompt: string;
  styleReferencePrompt: string;
  ageRange: string;
  characters: string[];
  storyPrompt: string;
}

interface ParsedStory {
  pages: StoryPage[];
  metadata: StoryMetadata;
}

interface PageImage {
  pageNumber: number;
  file: File | null;
  preview: string | null;
  existingUrl: string | null;
}

interface CharacterImage {
  name: string;
  file: File | null;
  preview: string | null;
  existingUrl: string | null;
}

const SUPABASE_PROJECT = "kwhyhflyyjhtbvbmtdmt";
const SUPABASE_IMG_URL = `https://${SUPABASE_PROJECT}.supabase.co/storage/v1/object/public/book-imgs`;

export default function UploadStoryPage() {
  const navigate = useNavigate();
  const params = useParams<{ id?: string }>();

  const [isEditMode, setIsEditMode] = createSignal(false);
  const [isLoading, setIsLoading] = createSignal(false);
  const [storyJson, setStoryJson] = createSignal("");
  const [parsedStory, setParsedStory] = createSignal<ParsedStory | null>(null);
  const [parseError, setParseError] = createSignal<string | null>(null);
  const [isUploading, setIsUploading] = createSignal(false);
  const [uploadError, setUploadError] = createSignal<string | null>(null);

  // Image states
  const [coverImage, setCoverImage] = createSignal<{ file: File | null; preview: string | null; existingUrl: string | null }>({ file: null, preview: null, existingUrl: null });
  const [pageImages, setPageImages] = createSignal<PageImage[]>([]);
  const [characterImages, setCharacterImages] = createSignal<CharacterImage[]>([]);
  const [showCharacterUpload, setShowCharacterUpload] = createSignal(false);

  // Load existing book data if in edit mode
  onMount(async () => {
    if (params.id) {
      setIsEditMode(true);
      setIsLoading(true);
      try {
        const book = await bookService.getBook(params.id);
        if (book && book.content) {
          // Build the story JSON from the book content
          const storyData = {
            pages: book.content.pages,
            metadata: book.content.metadata
          };
          const jsonString = JSON.stringify(storyData, null, 2);
          setStoryJson(jsonString);

          // Parse and set the story
          setParsedStory(storyData);

          // Set cover image from existing URL
          const coverUrl = `${SUPABASE_IMG_URL}/${book.id}/cover.jpg`;
          setCoverImage({ file: null, preview: null, existingUrl: coverUrl });

          // Set page images from existing URLs
          setPageImages(book.content.pages.map((page: StoryPage, index: number) => ({
            pageNumber: page.pageNumber,
            file: null,
            preview: null,
            existingUrl: page.imageUrl || `${SUPABASE_IMG_URL}/${book.id}/page_${index + 1}.png`
          })));

          // Set character images (check if they exist)
          if (book.content.metadata.characters && Array.isArray(book.content.metadata.characters)) {
            setCharacterImages(book.content.metadata.characters.map((name: string) => {
              const sanitizedName = name.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
              return {
                name,
                file: null,
                preview: null,
                existingUrl: `${SUPABASE_IMG_URL}/${book.id}/character_${sanitizedName}.png`
              };
            }));
          }
        }
      } catch (error) {
        console.error("Failed to load book:", error);
        setUploadError("Failed to load existing book data");
      } finally {
        setIsLoading(false);
      }
    }
  });

  const handleJsonInput = (value: string) => {
    setStoryJson(value);
    setParseError(null);

    if (!value.trim()) {
      setParsedStory(null);
      setPageImages([]);
      setCharacterImages([]);
      return;
    }

    try {
      const parsed = JSON.parse(value);

      // Validate required structure
      if (!parsed.pages || !Array.isArray(parsed.pages)) {
        throw new Error("Story must have a 'pages' array");
      }
      if (!parsed.metadata) {
        throw new Error("Story must have a 'metadata' object");
      }

      setParsedStory({
        pages: parsed.pages,
        metadata: parsed.metadata
      });

      // Initialize page images array, preserving existing URLs in edit mode
      const currentPageImages = pageImages();
      setPageImages(parsed.pages.map((page: StoryPage) => {
        const existing = currentPageImages.find(p => p.pageNumber === page.pageNumber);
        return {
          pageNumber: page.pageNumber,
          file: existing?.file || null,
          preview: existing?.preview || null,
          existingUrl: existing?.existingUrl || page.imageUrl || null
        };
      }));

      // Initialize character images array
      if (parsed.metadata.characters && Array.isArray(parsed.metadata.characters)) {
        const currentCharImages = characterImages();
        setCharacterImages(parsed.metadata.characters.map((name: string) => {
          const existing = currentCharImages.find(c => c.name === name);
          return {
            name,
            file: existing?.file || null,
            preview: existing?.preview || null,
            existingUrl: existing?.existingUrl || null
          };
        }));
      }
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Invalid JSON");
      setParsedStory(null);
      setPageImages([]);
      setCharacterImages([]);
    }
  };

  const handleCoverImageChange = (e: Event) => {
    const target = e.target as HTMLInputElement;
    const file = target.files?.[0] || null;

    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setCoverImage({ file, preview: reader.result as string, existingUrl: coverImage().existingUrl });
      };
      reader.readAsDataURL(file);
    } else {
      setCoverImage({ file: null, preview: null, existingUrl: coverImage().existingUrl });
    }
  };

  const handlePageImageChange = (pageNumber: number, e: Event) => {
    const target = e.target as HTMLInputElement;
    const file = target.files?.[0] || null;

    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setPageImages(prev => prev.map(p =>
          p.pageNumber === pageNumber
            ? { ...p, file, preview: reader.result as string }
            : p
        ));
      };
      reader.readAsDataURL(file);
    } else {
      setPageImages(prev => prev.map(p =>
        p.pageNumber === pageNumber
          ? { ...p, file: null, preview: null }
          : p
      ));
    }
  };

  const handleCharacterImageChange = (name: string, e: Event) => {
    const target = e.target as HTMLInputElement;
    const file = target.files?.[0] || null;

    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setCharacterImages(prev => prev.map(c =>
          c.name === name
            ? { ...c, file, preview: reader.result as string }
            : c
        ));
      };
      reader.readAsDataURL(file);
    } else {
      setCharacterImages(prev => prev.map(c =>
        c.name === name
          ? { ...c, file: null, preview: null }
          : c
      ));
    }
  };

  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64 = reader.result as string;
        // Remove the data URL prefix to get just the base64 content
        const base64Content = base64.split(',')[1];
        resolve(base64Content);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  const handleSubmit = async (e: Event) => {
    e.preventDefault();

    const story = parsedStory();
    if (!story) {
      setUploadError("Please provide valid story JSON");
      return;
    }

    // In create mode, require all images
    // In edit mode, only require images if there's no existing URL
    const hasCoverImage = coverImage().file || coverImage().existingUrl;
    if (!hasCoverImage) {
      setUploadError("Please upload a cover image");
      return;
    }

    // Check all pages have images (either new file or existing URL)
    const missingPages = pageImages().filter(p => !p.file && !p.existingUrl);
    if (missingPages.length > 0) {
      setUploadError(`Please upload images for pages: ${missingPages.map(p => p.pageNumber).join(', ')}`);
      return;
    }

    setIsUploading(true);
    setUploadError(null);

    try {
      // Only convert new images to base64
      const coverImageBase64 = coverImage().file ? await fileToBase64(coverImage().file!) : null;

      const pageImagesData = await Promise.all(
        pageImages()
          .filter(p => p.file) // Only include pages with new files
          .map(async (p) => ({
            pageNumber: p.pageNumber,
            imageBase64: await fileToBase64(p.file!)
          }))
      );

      const characterImagesData = await Promise.all(
        characterImages()
          .filter(c => c.file) // Only include characters with new files
          .map(async (c) => ({
            name: c.name,
            imageBase64: await fileToBase64(c.file!)
          }))
      );

      if (isEditMode() && params.id) {
        // Update existing book
        const result = await bookService.updateStory(params.id, {
          story,
          coverImageBase64: coverImageBase64 || undefined,
          pageImages: pageImagesData.length > 0 ? pageImagesData : undefined,
          characterImages: characterImagesData.length > 0 ? characterImagesData : undefined
        });

        if ((result as any).bookId) {
          navigate(`/book/${(result as any).bookId}`);
        } else {
          setUploadError("Update succeeded but no book ID returned");
        }
      } else {
        // Create new book - require all images
        if (!coverImageBase64) {
          setUploadError("Please upload a cover image");
          return;
        }

        const allPageImagesData = await Promise.all(
          pageImages().map(async (p) => {
            if (!p.file) {
              throw new Error(`Missing image for page ${p.pageNumber}`);
            }
            return {
              pageNumber: p.pageNumber,
              imageBase64: await fileToBase64(p.file)
            };
          })
        );

        const result = await bookService.uploadStory({
          story,
          coverImageBase64,
          pageImages: allPageImagesData,
          characterImages: characterImagesData.length > 0 ? characterImagesData : undefined
        });

        if ((result as any).bookId) {
          navigate(`/book/${(result as any).bookId}`);
        } else {
          setUploadError("Upload succeeded but no book ID returned");
        }
      }
    } catch (error) {
      console.error("Upload failed:", error);
      setUploadError(error instanceof Error ? error.message : "Upload failed. Please try again.");
    } finally {
      setIsUploading(false);
    }
  };

  const getDisplayImage = (file: File | null, preview: string | null, existingUrl: string | null) => {
    if (preview) return preview;
    if (existingUrl) return existingUrl;
    return null;
  };

  return (
    <div class="max-w-4xl mx-auto">
      <h1 class="text-3xl font-comic text-kiddy-primary mb-6 text-center">
        {isEditMode() ? 'Edit Story (Admin)' : 'Upload Story (Admin)'}
      </h1>

      <Show when={isLoading()}>
        <div class="text-center py-8">
          <span class="animate-pulse text-kiddy-primary font-comic text-xl">Loading book data...</span>
        </div>
      </Show>

      <Show when={!isLoading()}>
        <form onSubmit={handleSubmit} class="space-y-8 bg-gradient-to-br from-yellow-100 via-pink-100 to-blue-100 p-8 rounded-3xl shadow-2xl border-4 border-kiddy-primary/10">
          {/* Story JSON Input */}
          <div>
            <label class="block text-kiddy-primary text-lg mb-2 font-comic" for="storyJson">
              Story JSON
            </label>
            <textarea
              id="storyJson"
              rows={10}
              class="w-full p-3 border-2 border-kiddy-primary/30 rounded-xl focus:ring-2 focus:ring-kiddy-primary text-sm font-mono bg-white resize-y"
              placeholder='Paste your story JSON here...'
              value={storyJson()}
              onInput={(e) => handleJsonInput(e.currentTarget.value)}
            />
            <Show when={parseError()}>
              <p class="text-red-600 text-sm mt-1">{parseError()}</p>
            </Show>
          </div>

          {/* Parsed Story Display */}
          <Show when={parsedStory()}>
            <div class="space-y-6">
              {/* Story Metadata Summary */}
              <div class="bg-white/80 rounded-xl p-4 border border-kiddy-primary/20">
                <h2 class="text-xl font-comic text-kiddy-primary mb-2">
                  {parsedStory()!.metadata.title}
                </h2>
                <p class="text-gray-600 text-sm mb-2">{parsedStory()!.metadata.bookSummary}</p>
                <div class="flex gap-4 text-sm text-gray-500">
                  <span>Age: {parsedStory()!.metadata.ageRange}</span>
                  <span>Theme: {parsedStory()!.metadata.theme}</span>
                  <span>Pages: {parsedStory()!.pages.length}</span>
                </div>
              </div>

              {/* Cover Image Upload */}
              <div class="bg-white/80 rounded-xl p-4 border border-kiddy-primary/20">
                <h3 class="text-lg font-comic text-kiddy-primary mb-3">Book Cover</h3>
                <div class="flex gap-4 items-start">
                  <div class="flex-1">
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleCoverImageChange}
                      class="w-full p-2 border-2 border-dashed border-kiddy-primary/30 rounded-lg bg-white"
                    />
                    <p class="text-xs text-gray-500 mt-1">
                      Prompt: {parsedStory()!.metadata.coverImagePrompt}
                    </p>
                    <Show when={isEditMode() && !coverImage().file && coverImage().existingUrl}>
                      <p class="text-xs text-blue-600 mt-1">Using existing cover image (upload new to replace)</p>
                    </Show>
                  </div>
                  <Show when={getDisplayImage(coverImage().file, coverImage().preview, coverImage().existingUrl)}>
                    <img
                      src={getDisplayImage(coverImage().file, coverImage().preview, coverImage().existingUrl)!}
                      alt="Cover preview"
                      class="w-24 h-32 object-cover rounded-lg border-2 border-kiddy-primary/30"
                    />
                  </Show>
                </div>
              </div>

              {/* Page Images */}
              <div class="space-y-4">
                <h3 class="text-lg font-comic text-kiddy-primary">Page Images</h3>
                <For each={parsedStory()!.pages}>
                  {(page) => {
                    const pageImage = () => pageImages().find(p => p.pageNumber === page.pageNumber);
                    const displayImage = () => {
                      const img = pageImage();
                      return img ? getDisplayImage(img.file, img.preview, img.existingUrl) : null;
                    };
                    return (
                      <div class="bg-white/80 rounded-xl p-4 border border-kiddy-primary/20">
                        <div class="flex gap-4">
                          <div class="flex-1">
                            <h4 class="font-comic text-kiddy-primary mb-2">
                              Page {page.pageNumber}
                            </h4>
                            <p class="text-gray-700 text-sm whitespace-pre-line mb-3 bg-gray-50 p-3 rounded-lg">
                              {page.text}
                            </p>
                            <input
                              type="file"
                              accept="image/*"
                              onChange={(e) => handlePageImageChange(page.pageNumber, e)}
                              class="w-full p-2 border-2 border-dashed border-kiddy-primary/30 rounded-lg bg-white"
                            />
                            <p class="text-xs text-gray-500 mt-1 line-clamp-2">
                              Prompt: {page.imagePrompt}
                            </p>
                            <Show when={isEditMode() && !pageImage()?.file && pageImage()?.existingUrl}>
                              <p class="text-xs text-blue-600 mt-1">Using existing image (upload new to replace)</p>
                            </Show>
                          </div>
                          <Show when={displayImage()}>
                            <img
                              src={displayImage()!}
                              alt={`Page ${page.pageNumber} preview`}
                              class="w-32 h-32 object-cover rounded-lg border-2 border-kiddy-primary/30"
                            />
                          </Show>
                        </div>
                      </div>
                    );
                  }}
                </For>
              </div>

              {/* Character Images (Optional) */}
              <div class="bg-white/80 rounded-xl p-4 border border-kiddy-primary/20">
                <button
                  type="button"
                  onClick={() => setShowCharacterUpload(!showCharacterUpload())}
                  class="flex items-center gap-2 text-lg font-comic text-kiddy-primary mb-3"
                >
                  <span>{showCharacterUpload() ? '▼' : '▶'}</span>
                  Character Images (Optional)
                </button>

                <Show when={showCharacterUpload()}>
                  <div class="space-y-4">
                    <For each={characterImages()}>
                      {(character) => {
                        const displayImage = () => getDisplayImage(character.file, character.preview, character.existingUrl);
                        return (
                          <div class="flex gap-4 items-center">
                            <div class="flex-1">
                              <label class="block text-sm font-medium text-gray-700 mb-1">
                                {character.name}
                              </label>
                              <input
                                type="file"
                                accept="image/*"
                                onChange={(e) => handleCharacterImageChange(character.name, e)}
                                class="w-full p-2 border-2 border-dashed border-kiddy-primary/30 rounded-lg bg-white"
                              />
                              <Show when={isEditMode() && !character.file && character.existingUrl}>
                                <p class="text-xs text-blue-600 mt-1">Using existing image (upload new to replace)</p>
                              </Show>
                            </div>
                            <Show when={displayImage()}>
                              <img
                                src={displayImage()!}
                                alt={`${character.name} preview`}
                                class="w-16 h-16 object-cover rounded-lg border-2 border-kiddy-primary/30"
                              />
                            </Show>
                          </div>
                        );
                      }}
                    </For>
                  </div>
                </Show>
              </div>
            </div>
          </Show>

          {/* Upload Error */}
          <Show when={uploadError()}>
            <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-xl">
              {uploadError()}
            </div>
          </Show>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={!parsedStory() || isUploading()}
            class="w-full bg-gradient-to-r from-kiddy-primary to-kiddy-secondary text-white font-comic text-xl py-4 rounded-full shadow-lg hover:scale-105 transition-transform duration-300 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
          >
            {isUploading() ? (
              <span class="animate-pulse">{isEditMode() ? 'Updating Story...' : 'Uploading Story...'}</span>
            ) : (
              isEditMode() ? 'Update Story' : 'Upload Story'
            )}
          </button>
        </form>
      </Show>
    </div>
  );
}
