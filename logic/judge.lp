% logic/judge.lp — judge decision logic in ASP (clingo); mirrors
% logic/judge_program.py minidatalog rules. Each rule cites the p5_judge.py line.
% Primitives (cand, samefam, opposed, sharedrel, nvm2, forkaxis, crosstheory) are
% materialised from the ported p5 functions (bounded treatment, VJ1.2).

% p5:159 fam_same = same_family(...)
notsamefam(A,B) :- cand(A,B), not samefam(A,B).
% p5:161 axis in FORK_AXES and not fam_same
fork(A,B) :- cand(A,B), forkaxis(A), notsamefam(A,B).
% p5:161 axis in FORK_AXES and opposed
fork(A,B) :- cand(A,B), forkaxis(A), opposed(A,B).
% p5:166 continue after fork
skipcorr(A,B) :- fork(A,B).
% p5:167-168 if opposed: continue
skipcorr(A,B) :- cand(A,B), opposed(A,B).
% p5:173 formal if nvm>=2 (same_family, not skipped)
formalraw(A,B) :- cand(A,B), samefam(A,B), nvm2(A,B), not skipcorr(A,B).
% p5:173 partial if shared_rel
haspartial(A,B) :- cand(A,B), samefam(A,B), sharedrel(A,B), not skipcorr(A,B).
% p5:173 partial only when not formal
partialonly(A,B) :- haspartial(A,B), not formalraw(A,B).
% p5:173,175 generative otherwise (incl. not fam_same)
generative(A,B) :- cand(A,B), not skipcorr(A,B), not formalraw(A,B), not haspartial(A,B).
% p5:178-179 cross-theory formal hard-capped to partial
corr(A,B,"partial") :- formalraw(A,B), crosstheory().
% p5:177 within-theory formal stands
corr(A,B,"formal") :- formalraw(A,B), not crosstheory().
% p5:173 partial
corr(A,B,"partial") :- partialonly(A,B).
% p5:173,175 generative
corr(A,B,"generative") :- generative(A,B).
