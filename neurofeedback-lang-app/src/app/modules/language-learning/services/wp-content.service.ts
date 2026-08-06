// src/app/modules/language-learning/services/wp-content.service.ts
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { tap, map, catchError } from 'rxjs/operators';
interface WpContent {
  id: number;
  title: string;
  content: string;
  excerpt: string;
}

interface RawWpPost {
  id: number;
  title: {
    rendered: string;
  };
  content: {
    rendered: string;
  };
  excerpt: {
    rendered: string;
  };
  // Add other properties as needed from the WordPress API response
}

@Injectable({
  providedIn: 'root'
})
export class WpContentService {
  private cache: { [url: string]: WpContent[] } = {};

  constructor(private http: HttpClient) { }

  getWpContent(url: string): Observable<WpContent[] | undefined> {
    if (this.cache[url]) {
      return of(this.cache[url]);
    }

    return this.http.get<RawWpPost[]>(url).pipe(
      tap(posts => this.cache[url] = this._transformWpPosts(posts)),
      map(posts => this._transformWpPosts(posts)),
      catchError(error => {
        console.error('Error fetching WordPress content:', error);
        return of(undefined);
      })
    );
  }

  private _transformWpPosts(posts: RawWpPost[]): WpContent[] {
    return posts.map(post => ({
      id: post.id,
      title: post.title.rendered,
      content: post.content.rendered,
      excerpt: post.excerpt.rendered
    }));
  }
}
