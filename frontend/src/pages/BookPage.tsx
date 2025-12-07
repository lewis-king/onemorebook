import { createResource, createSignal, Show, createEffect } from "solid-js";
import { useParams } from "@solidjs/router";
import { bookService } from "../services/api";
import { BookSpread } from "../components/BookPage/BookSpread";
import PageControls from "../components/BookPage/PageControls";
// import StarRating from "../components/StarRating";

export default function BookPage() {
    const params = useParams();
    // Guard: only fetch if params.id is defined and not 'undefined'
    const validId = params.id && params.id !== 'undefined';
    const [book] = createResource(() => validId ? params.id : undefined, bookService.getBook);
    const [currentPage, setCurrentPage] = createSignal(0);
    const [error, setError] = createSignal<string | null>(null);
    const [pageFlipInstance, setPageFlipInstance] = createSignal<any>(null);
    const [stars, setStars] = createSignal<number>(0);

    // Sync stars signal with book data when book loads/changes
    createEffect(() => {
        if (book() && typeof book().stars === 'number') {
            setStars(book().stars);
        }
    });

    // Helper to extract page content and images from new structure
    const getPages = () => {
        const b = book();
        if (!b || !b.content || !Array.isArray(b.content.pages)) return [];
        // Insert a placeholder for the cover at index 0, then all story pages, then a placeholder for the rating/ending page
        return [""]
            .concat(b.content.pages.map(p => p.text || ""))
            .concat([""]); // for the rating/ending page
    };
    const getPageImages = () => {
        const b = book();
        if (!b || !b.content || !Array.isArray(b.content.pages)) return [];
        const baseUrl = `https://kwhyhflyyjhtbvbmtdmt.supabase.co/storage/v1/object/public/book-imgs/${b.id}`;
        // First image is the cover, then the rest are story pages. No placeholder at the end!
        return [{ url: getCoverImage() }]
            .concat(b.content.pages.map((page, i) => ({
                url: page.imageUrl || `${baseUrl}/page_${i+1}.png`,
                fallbackUrl: `${baseUrl}/page${i+1}.jpg`
            })));
    };
    const getCoverImage = () => {
        const b = book();
        return `https://kwhyhflyyjhtbvbmtdmt.supabase.co/storage/v1/object/public/book-imgs/${b?.id ?? ''}/cover.jpg`;
    };

    const handleUpvote = async (id: string, currentStars: number) => {
        try {
            const updated = await bookService.updateStars(id, currentStars);
            setStars(updated.stars);
        } catch (e) {
            console.error('Error updating stars:', e);
            setError(e instanceof Error ? e.message : 'Failed to update stars');
        }
    };


    // Helper for Next/Back with animation
    const handlePrevious = () => {
        const flip = pageFlipInstance();
        if (flip && flip.flipPrev) {
            flip.flipPrev();
        } else if (currentPage() > 0) {
            setCurrentPage(currentPage() - 1);
        }
    };
    const handleNext = () => {
        const flip = pageFlipInstance();
        if (flip && flip.flipNext) {
            flip.flipNext();
        } else if (currentPage() < getPages().length - 1) {
            setCurrentPage(currentPage() + 1);
        }
    };

    return (
        <div class="w-full max-w-[1600px] mx-auto px-4 lg:px-12 flex flex-col items-center justify-center">
            <Show when={error()}>
                <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
                    {error()}
                </div>
            </Show>

            {/* Add PageControls above the book */}
            <Show when={!book.loading && book()}>
                <PageControls
                    currentPage={currentPage()}
                    totalPages={getPages().length}
                    onPrevious={handlePrevious}
                    onNext={handleNext}
                />
            </Show>

            <Show
                when={!book.loading && book()}
                fallback={
                    <div class="text-center py-8">
                        Loading book...
                    </div>
                }
            >
                <BookSpread
                    pages={getPages()}
                    coverImage={getCoverImage()}
                    pageImages={getPageImages()}
                    onPageFlipInit={setPageFlipInstance}
                    onPageChange={setCurrentPage}
                    bookId={book()?.id ?? ''}
                    stars={stars()}
                    onUpvote={handleUpvote}
                    currentPage={currentPage()} // Pass currentPage prop
                />
            </Show>
        </div>
    );
}